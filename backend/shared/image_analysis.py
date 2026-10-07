"""SQL authority and immutable objects for full image analysis."""
import json
from datetime import datetime, timedelta
from shared.database import SessionLocal
from shared.models import Job, JobStatus, ImageAnalysisRun as Run, ImageAnalysisStep as Step, EngineUsage, User
from shared.minio_client import get_minio_client
from shared.image_full import resolve_steps, coverage, report, fingerprint, TERMINAL
from shared import face_analysis as facial


class LostLease(RuntimeError):
    pass


def put_json(storage, path, value):
    data = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
    if not storage.upload_file(bucket_name=storage.bucket_results, object_name=path,
                               file_data=data, content_type='application/json'):
        raise RuntimeError('Image result persistence unavailable')
    import hashlib
    expected = hashlib.sha256(data).hexdigest()
    if hashlib.sha256(storage.download_file(storage.bucket_results, path)).hexdigest() != expected:
        raise RuntimeError('Image result checksum mismatch')
    return expected


def locked(db, job_id):
    job = db.query(Job).filter(Job.id == job_id).with_for_update().first()
    run = db.query(Run).filter(Run.job_id == job_id).with_for_update().first() if job else None
    return job, run


def check(db, job, run, holder, fence, *, deadline=True):
    now = datetime.utcnow()
    if not job or not run or run.status in TERMINAL or run.holder != holder or run.fence != fence:
        raise LostLease('lost_lease')
    if run.cancel_requested:
        raise LostLease('cancelled')
    if deadline and run.deadline_at <= now:
        raise LostLease('deadline')
    if run.lease_until is None or run.lease_until <= now:
        raise LostLease('lost_lease')
    user = db.get(User, job.user_id)
    if not user or not user.is_active:
        raise LostLease('owner_unavailable')
    if run.usage_id:
        usage = db.get(EngineUsage, run.usage_id)
        if not usage or usage.status != 'running' or usage.holder != holder:
            raise LostLease('accounting_claim_lost')


def add_steps(db, job_id, items):
    for item in items:
        db.add(Step(job_id=job_id, step_id=item['step_id'], task=item['task'], input=item['input'],
                    status=item['status'], reason_code=item.get('reason_code'),
                    step_kind='face' if item['task'] in facial.FACIAL_TASKS else 'florence',
                    provider=facial.provider(item['task'])))


def claim(job_id, holder, session_factory=None):
    with (session_factory or SessionLocal)() as db:
        job, run = locked(db, job_id)
        now = datetime.utcnow()
        if not run or run.status in TERMINAL or (run.holder and run.lease_until and run.lease_until > now):
            return None
        run.fence += 1
        run.holder, run.lease_until = holder, now + timedelta(seconds=30)
        run.status = 'processing'
        job.status = JobStatus.PROCESSING
        job.started_at = job.started_at or now
        if not db.query(Step).filter(Step.job_id == job_id).first():
            add_steps(db, job_id, facial.initial_steps(run.options))
        # Running steps are uncertain, not evidence of a completed inference.
        for row in db.query(Step).filter(Step.job_id == job_id, Step.status == 'running'):
            if row.attempts >= 2:
                row.status, row.reason_code = 'failed', 'uncertain_attempt'
            else:
                row.status = 'pending'
        db.commit()
        return run.fence, dict(run.options), run.source_path, run.deadline_at, run.usage_id


def guard(job_id, holder, fence, session_factory=None):
    with (session_factory or SessionLocal)() as db:
        job, run = locked(db, job_id)
        check(db, job, run, holder, fence)
        run.lease_until = datetime.utcnow() + timedelta(seconds=30)
        db.commit()


def next_step(job_id, holder, fence, session_factory=None):
    with (session_factory or SessionLocal)() as db:
        job, run = locked(db, job_id)
        check(db, job, run, holder, fence)
        row = db.query(Step).filter(Step.job_id == job_id, Step.status == 'pending').order_by((Step.step_kind == 'florence').asc(), Step.id).first()
        if not row:
            return None
        limits = facial.call_limits(run.options)
        calls = dict(run.calls_by_provider or {})
        # Old runs already counted Florence calls before provider counters existed.
        florence_calls = calls.get('florence', run.calls_started if facial.profile(run.options) == 'image-full-v1' else 0)
        facial_calls = sum(v for k, v in calls.items() if k != 'florence')
        branch_limit = limits['florence'] if row.step_kind == 'florence' else limits['face']
        branch_calls = florence_calls if row.step_kind == 'florence' else facial_calls
        if run.calls_started >= limits['total'] or branch_calls >= branch_limit:
            row.status, row.reason_code = 'skipped', 'call_limit'
            db.commit()
            return 'limit'
        run.calls_started += 1
        calls[row.provider] = calls.get(row.provider, 0) + 1
        run.calls_by_provider = calls
        row.status, row.attempts = 'running', row.attempts + 1
        run.lease_until = datetime.utcnow() + timedelta(seconds=30)
        data = {'step_id': row.step_id, 'task': row.task, 'input': dict(row.input), 'attempts': row.attempts}
        db.commit()
        return data


def save_step(job_id, holder, fence, item, output, storage, *, reason=None, session_factory=None):
    value = {**item, **(output or {}), 'status': 'failed' if reason else 'succeeded', 'reason_code': reason}
    path = f"images/{job_id}/steps/{item['step_id']}/{fence}-{fingerprint(value)}.json"
    from shared.schemas import ImageFullStepResult
    if item['task'] in facial.FACIAL_TASKS:
        value = facial.step_result(value)
        facial.FaceStepResult.model_validate(value)
    else:
        ImageFullStepResult.model_validate(value)
    checksum = put_json(storage, path, value)
    try:
        _publish_step(job_id, holder, fence, item, value, path, checksum, session_factory)
    except Exception:
        discard_object(storage, path)
        raise


def discard_object(storage, path):
    try:
        storage.delete_file(storage.bucket_results, path)
    except Exception:
        pass  # Retention/purge also removes unselected immutable objects.


def _publish_step(job_id, holder, fence, item, value, path, checksum, session_factory):
    with (session_factory or SessionLocal)() as db:
        job, run = locked(db, job_id)
        check(db, job, run, holder, fence)
        row = db.query(Step).filter(Step.job_id == job_id, Step.step_id == item['step_id']).one()
        row.status, row.reason_code = value['status'], value['reason_code']
        row.result_path, row.result_hash, row.duration_ms = path, checksum, value.get('duration_ms', 0)
        rows = db.query(Step).filter(Step.job_id == job_id).all()
        job.progress = max(job.progress or 0, min(95, int(95 * sum(r.status != 'pending' and r.status != 'running' for r in rows) / max(len(rows), 15))))
        db.commit()


def step_snapshot(db, job_id):
    return [{'step_id': row.step_id, 'task': row.task, 'input': dict(row.input), 'status': row.status,
             'reason_code': row.reason_code, 'attempts': row.attempts, 'duration_ms': row.duration_ms,
             'result_path': row.result_path, 'result_hash': row.result_hash}
            for row in db.query(Step).filter(Step.job_id == job_id).order_by(Step.id)]


def read_steps(rows, storage):
    import hashlib
    results = []
    for row in rows:
        value = {k: v for k, v in row.items() if k not in ('result_path', 'result_hash')}
        if row['result_path']:
            try:
                raw = storage.download_file(storage.bucket_results, row['result_path'])
            except Exception as exc:
                if isinstance(exc, KeyError) or getattr(exc, 'code', None) in ('NoSuchKey', 'NoSuchObject'):
                    value.update(status='failed', reason_code='checkpoint_unavailable')
                    results.append(value)
                    continue
                raise
            if hashlib.sha256(raw).hexdigest() != row['result_hash']:
                value.update(status='failed', reason_code='checkpoint_checksum_mismatch')
            else:
                try:
                    value = json.loads(raw)
                    from shared.schemas import ImageFullStepResult
                    if value['task'] in facial.FACIAL_TASKS:
                        facial.FaceStepResult.model_validate(facial.step_result(value))
                    else:
                        ImageFullStepResult.model_validate(value)
                except (ValueError, TypeError):
                    value = {**{k: v for k, v in row.items() if k not in ('result_path', 'result_hash')},
                             'status': 'failed', 'reason_code': 'checkpoint_invalid'}
        results.append(value)
    return results


def load_steps(db, job_id, storage):
    return read_steps(step_snapshot(db, job_id), storage)


def resolve(job_id, holder, fence, storage, session_factory=None):
    factory = session_factory or SessionLocal
    with factory() as db:
        job, run = locked(db, job_id)
        check(db, job, run, holder, fence)
        if run.resolved or facial.profile(run.options) == 'image-faces-v1':
            return False
        rows, options, width, height = step_snapshot(db, job_id), dict(run.options['full_options']), run.width, run.height
        db.commit()
    items, inputs = resolve_steps(read_steps(rows, storage), options, width, height)
    with factory() as db:
        job, run = locked(db, job_id)
        check(db, job, run, holder, fence)
        if run.resolved or facial.profile(run.options) == 'image-faces-v1':
            return False
        add_steps(db, job_id, items)
        run.resolved_inputs, run.resolved = inputs, True
        db.commit()
        return True


def resolve_faces(job_id, holder, fence, storage, session_factory=None):
    """Freeze face IDs/crops once from the durable detector checkpoint."""
    factory = session_factory or SessionLocal
    with factory() as db:
        job, run = locked(db, job_id)
        check(db, job, run, holder, fence)
        if facial.profile(run.options) == 'image-full-v1' or run.faces_resolved:
            return False
        rows = step_snapshot(db, job_id)
        detector = next((r for r in rows if r['task'] == 'face_detection'), None)
        if detector is None or detector['status'] in ('pending', 'running'):
            return False
        options = facial.face_options(run.options)
        db.commit()
    detection = read_steps([detector], storage)[0]
    items = facial.dependent_steps(detection, options)
    with factory() as db:
        job, run = locked(db, job_id)
        check(db, job, run, holder, fence)
        if run.faces_resolved:
            return False
        add_steps(db, job_id, items)
        run.faces_resolved = True
        db.commit()
        return bool(items)


def terminal_reason(db, job, run, holder, fence, reason, recovery):
    now = datetime.utcnow()
    if not job or not run or run.status in TERMINAL or run.holder != holder or run.fence != fence:
        raise LostLease('lost_lease')
    if not run.lease_until or run.lease_until <= now:
        raise LostLease('lost_lease')
    if run.usage_id and not recovery:
        usage = db.get(EngineUsage, run.usage_id)
        if not usage or usage.status != 'running' or usage.holder != holder:
            raise LostLease('accounting_claim_lost')
    if run.cancel_requested:
        return 'cancelled'
    if run.deadline_at <= now:
        return 'deadline'
    user = db.get(User, job.user_id)
    if not user or not user.is_active:
        return 'owner_unavailable'
    return reason


def finish(job_id, holder, fence, storage, *, reason=None, recovery=False, session_factory=None):
    """Persist outside SQL locks, then fence and revalidate at the final commit.

    A watchdog may publish diagnostics without taking the interrupted compute's
    accounting claim. It never publishes a successful compute result that way.
    """
    factory = session_factory or SessionLocal
    with factory() as db:
        job, run = locked(db, job_id)
        try:
            reason = terminal_reason(db, job, run, holder, fence, reason, recovery)
        except LostLease:
            return None
        if recovery and not reason:
            return None
        snapshot = {'options': dict(run.options), 'width': run.width, 'height': run.height,
                    'preview_path': run.preview_path, 'resolved_inputs': dict(run.resolved_inputs),
                    'calls_started': run.calls_started, 'calls_by_provider': dict(run.calls_by_provider or {}), 'source_sha256': job.file_checksum or '',
                    'started_at': job.started_at or job.created_at, 'filename': job.filename, 'mime_type': job.mime_type or 'image/png', 'size_bytes': job.file_size_bytes or 0}
        rows = step_snapshot(db, job_id)
        db.commit()
    results = read_steps(rows, storage)
    import base64
    preview = None
    if snapshot['preview_path']:
        try:
            raw = storage.download_file(storage.bucket_results, snapshot['preview_path'])
            import hashlib
            expected = snapshot['preview_path'].rsplit('/', 1)[-1].split('-', 1)[-1].split('.')[0]
            if hashlib.sha256(raw).hexdigest() != expected:
                reason = reason or 'preview_checksum_mismatch'
            else:
                preview = base64.b64encode(raw).decode()
        except Exception as exc:
            if isinstance(exc, KeyError) or getattr(exc, 'code', None) in ('NoSuchKey', 'NoSuchObject'):
                reason = reason or 'preview_unavailable'
            else:
                raise
    # Deadline or cancellation can arrive during object I/O. Rebuild the envelope
    # with the new reason instead of committing the earlier successful report.
    for _ in range(3):
        prepared = []
        for result in results:
            if result['status'] in ('pending', 'running'):
                result = {**result, 'status': 'skipped', 'reason_code': reason or 'dependency_failed'}
            prepared.append(result)
        from shared.vision_capabilities import VISION_TASKS
        from shared.image_full import step
        selected_profile = facial.profile(snapshot['options'])
        expected_tasks = list(VISION_TASKS) if selected_profile != 'image-faces-v1' else []
        if selected_profile != 'image-full-v1':
            expected_tasks += list(facial.FACIAL_TASKS) if facial.face_options(snapshot['options'])['mode'] == 'expressions' else ['face_detection']
        for task in expected_tasks:
            if not any(r['task'] == task for r in prepared):
                prepared.append({**step(task), 'status': 'skipped', 'reason_code': reason or 'dependency_failed', 'attempts': 0})
        cov = coverage(prepared)
        face_block = None
        if selected_profile != 'image-full-v1':
            face_block = facial.block(prepared, snapshot['options'])
            if selected_profile == 'image-faces-v1':
                cov = face_block['coverage']
            else:
                cov = {**cov, 'task_families_total': 18,
                       'task_families_completed': cov['task_families_completed'] + face_block['coverage']['task_families_completed'],
                       'families': cov['families'] + face_block['coverage']['families']}
        status = 'cancelled' if reason == 'cancelled' else (
            'completed' if not reason and cov['task_families_completed'] == cov['task_families_total'] else
            'partial' if any(r['status'] == 'succeeded' for r in prepared) else 'failed')
        image = {'operation': 'full_analysis', 'schema_version': 'image-full-result-v1', 'profile': 'image-full-v1',
                 'analysis_status': status, 'task': 'full', 'task_label': 'Full Analysis', 'width': snapshot['width'], 'height': snapshot['height'],
                 'model': snapshot['options']['model'], 'duration_ms': int((datetime.utcnow()-snapshot['started_at']).total_seconds()*1000),
                 'image_base64': preview, 'image_mime_type': 'image/png', 'results': prepared,
                 'coverage': cov, 'resolved_inputs': snapshot['resolved_inputs'], 'request': snapshot['options'].get('full_options', snapshot['options'].get('face_options', {})),
                 'calls_started': snapshot['calls_started'], 'source_sha256': snapshot['source_sha256'], 'frame_policy': 'first_frame',
                 'reason_code': reason}
        if selected_profile == 'image-faces-v1':
            image = {**face_block, **{k: image[k] for k in ('width', 'height', 'duration_ms', 'image_base64', 'image_mime_type', 'analysis_status', 'calls_started', 'source_sha256', 'frame_policy', 'reason_code')},
                     'operation': 'face_analysis', 'profile': selected_profile, 'schema_version': 'face-result-v1',
                     'calls_by_provider': snapshot['calls_by_provider']}
        elif selected_profile == 'image-full-v2':
            image.update(profile=selected_profile, schema_version='image-full-result-v2', faces=face_block,
                         models=[{'provider': 'florence', **snapshot['options']['model']}, *face_block['models']],
                         calls_by_provider=snapshot['calls_by_provider'],
                         results=[facial.step_result(r) if r['task'] in facial.FACIAL_TASKS else {**r, 'kind': 'florence'} for r in prepared])
        image['description'] = next((r.get('text', '') for task in ('<MORE_DETAILED_CAPTION>', '<DETAILED_CAPTION>', '<CAPTION>')
            for r in prepared if r['task'] == task and r['status'] == 'succeeded' and r.get('text')), '')
        image['text'] = image['description']
        image['lines'], image['regions'] = [], []
        native_report = report([r for r in prepared if r['task'] not in facial.FACIAL_TASKS], status) if selected_profile != 'image-faces-v1' else '# Rostos e expressões\n'
        payload = {'markdown': native_report + ('\n\n' + facial.markdown(face_block) if face_block else ''), 'image': image,
                   'metadata': {'title': snapshot['filename'], 'format': snapshot['mime_type'], 'size_bytes': snapshot['size_bytes'], 'analysis_status': status, 'reason_code': reason}}
        from shared.schemas import ImageFullAnalysisResult
        if selected_profile == 'image-faces-v1':
            image = facial.FaceAnalysisResult.model_validate(image).model_dump(mode='json')
        elif selected_profile == 'image-full-v2':
            from shared.schemas import ImageFullV2Result
            image = ImageFullV2Result.model_validate(image).model_dump(mode='json')
        else:
            ImageFullAnalysisResult.model_validate(image)
        payload['image'] = image
        from shared.schemas import ConversionResult
        ConversionResult.model_validate(payload)
        path = f'images/{job_id}/reports/{fence}-{fingerprint(payload)}.json'
        put_json(storage, path, payload)
        with factory() as db:
            job, run = locked(db, job_id)
            try:
                current = terminal_reason(db, job, run, holder, fence, reason, recovery)
            except LostLease:
                db.rollback()
                discard_object(storage, path)
                return None
            if current != reason:
                reason = current
                db.rollback()
                discard_object(storage, path)
                continue
            existing = {row.step_id: row for row in db.query(Step).filter(Step.job_id == job_id)}
            for item in prepared:
                if item['step_id'] not in existing:
                    add_steps(db, job_id, [item])
                elif item['status'] != existing[item['step_id']].status:
                    row = existing[item['step_id']]
                    row.status, row.reason_code = item['status'], item.get('reason_code')
            job.minio_result_path, job.char_count = path, len(payload['markdown'])
            job.status, job.progress, job.completed_at = JobStatus(status), 100, datetime.utcnow()
            run.status, run.holder, run.lease_until = status, None, None
            db.commit()
        break
    else:
        return None
    try:
        from shared.redis_client import get_redis_client
        cache = get_redis_client()
        cache.set_job_result(job_id, payload)
        cache.set_job_status(job_id=job_id, job_type='main', status=status, progress=100)
    except Exception:
        pass
    from shared.datalake.service import enqueue_export
    enqueue_export(job_id, session_factory=session_factory)
    return payload


def progress(db, job_id):
    run = db.get(Run, job_id)
    if not run:
        return None
    steps = db.query(Step).filter(Step.job_id == job_id).all()
    return {'profile': facial.profile(run.options), 'calls_by_provider': run.calls_by_provider or {}, 'status': run.status, 'steps_total': len(steps), 'steps_completed': sum(r.status in ('succeeded', 'failed', 'skipped', 'not_applicable') for r in steps),
            'calls_started': run.calls_started, 'cancel_requested': run.cancel_requested, 'deadline_at': run.deadline_at.isoformat() + 'Z'}
