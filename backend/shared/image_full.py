"""Bounded Florence full-analysis planning. No model, API or worker imports."""
import hashlib
import json
import math
from shared.vision_capabilities import VISION_TASKS

PROFILE = 'image-full-v1'
MAX_CALLS = 32
BASE_TASKS = tuple(task for task, meta in VISION_TASKS.items() if meta[2] == 'none')
TEXT_TASKS = ('<OPEN_VOCABULARY_DETECTION>', '<REFERRING_EXPRESSION_SEGMENTATION>')
REGION_TASKS = tuple(task for task, meta in VISION_TASKS.items() if meta[2] == 'region')
TERMINAL = ('completed', 'partial', 'failed', 'cancelled')


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def step(task, index=0, **inputs):
    return {'step_id': task.strip('<>').lower() + f'-{index}', 'task': task,
            'input': inputs, 'status': 'pending'}


def initial_steps():
    return [step(task) for task in BASE_TASKS]


def clip_text(text, limit=2000):
    if len(text) <= limit:
        return text
    head = text[:limit]
    sentence = max(head.rfind('. '), head.rfind('? '), head.rfind('! '), head.rfind('\n'))
    if sentence >= limit // 2:
        return head[:sentence+1].strip()
    return head.rsplit(' ', 1)[0].strip() if ' ' in head else head


def resolve_steps(results, options, width, height):
    """Freeze the second phase once. Derived inputs always retain provenance."""
    by_task = {r['task']: r for r in results if r['status'] == 'succeeded'}
    captions = [by_task[t] for t in ('<MORE_DETAILED_CAPTION>', '<DETAILED_CAPTION>', '<CAPTION>')
                if t in by_task and by_task[t].get('text', '').strip()]
    caption = captions[0]['text'].strip() if captions else ''
    caption_origin = captions[0]['step_id'] if captions else None
    queries, regions, omitted, considered = [], [], [], []
    if options.get('queries'):
        queries = [{'text_input': q, 'origin': 'user'} for q in options['queries']]
    else:
        for task, origin in (('<OD>', 'object_detection'), ('<DENSE_REGION_CAPTION>', 'dense_region_caption')):
            for item in by_task.get(task, {}).get('regions', []):
                text = ' '.join(item.get('label', '').split())
                if text and text not in [q['text_input'] for q in queries]:
                    queries.append({'text_input': clip_text(text), 'origin': origin,
                                    'source_step_id': by_task[task]['step_id'], 'input_truncated': len(text) > 2000})
        if not queries and caption:
            queries = [{'text_input': clip_text(caption), 'origin': 'caption', 'source_step_id': caption_origin,
                        'input_truncated': len(caption) > 2000}]
    considered.extend(queries)
    if len(queries) > 3:
        omitted += queries[3:]
        queries = queries[:3]
    if options.get('regions'):
        regions = [{'region': box, 'origin': 'user'} for box in options['regions']]
        considered.extend(regions)
    else:
        regions = [{'region': [0, 0, 1, 1], 'origin': 'full_image'}]
        considered.extend(regions)
        candidates = []
        for task, origin in (('<OD>', 'object_detection'), ('<DENSE_REGION_CAPTION>', 'dense_region_caption'), ('<REGION_PROPOSAL>', 'region_proposal')):
            items = by_task.get(task, {}).get('regions', [])
            items = sorted(enumerate(items), key=lambda pair: (-float(pair[1].get('score', 0) or 0), pair[0]))
            for _, item in items:
                raw = item.get('bbox')
                if not raw or len(raw) != 4 or not width or not height:
                    continue
                box = [raw[0]/width, raw[1]/height, raw[2]/width, raw[3]/height]
                if not all(math.isfinite(v) and 0 <= v <= 1 for v in box) or box[0] >= box[2] or box[1] >= box[3]:
                    continue
                candidate = {'region': box, 'origin': origin, 'source_step_id': by_task[task]['step_id']}
                considered.append(candidate)
                if not any(iou(box, r['region']) >= .85 for r in candidates):
                    candidates.append(candidate)
                else:
                    omitted.append({**candidate, 'reason_code': 'duplicate_region'})
        regions += candidates[:3]
        omitted += candidates[3:]
    grounding = '. '.join(options['queries']) if options.get('queries') else clip_text(caption)
    planned = []
    captions_valid = all(t in by_task for t in ('<CAPTION>', '<DETAILED_CAPTION>', '<MORE_DETAILED_CAPTION>'))
    queries_valid = captions_valid and all(t in by_task for t in ('<OD>', '<DENSE_REGION_CAPTION>'))
    if grounding:
        planned.append(step('<CAPTION_TO_PHRASE_GROUNDING>', text_input=grounding,
                            origin='user' if options.get('queries') else 'caption',
                            source_step_id=None if options.get('queries') else caption_origin,
                            input_truncated=not options.get('queries') and len(caption) > 2000))
    else:
        item = step('<CAPTION_TO_PHRASE_GROUNDING>')
        item.update(status='not_applicable' if captions_valid else 'skipped',
                    reason_code='no_valid_text_input' if captions_valid else 'dependency_failed')
        planned.append(item)
    for task in TEXT_TASKS:
        if queries:
            planned.extend(step(task, i, **query) for i, query in enumerate(queries))
        else:
            item = step(task)
            item.update(status='not_applicable' if queries_valid else 'skipped',
                        reason_code='no_valid_text_input' if queries_valid else 'dependency_failed')
            planned.append(item)
    for task in REGION_TASKS:
        planned.extend(step(task, i, **region) for i, region in enumerate(regions))
    return planned, {'queries': queries, 'regions': regions, 'omitted_candidates': omitted, 'considered_candidates': considered}


def iou(a, b):
    intersection = max(0, min(a[2], b[2])-max(a[0], b[0])) * max(0, min(a[3], b[3])-max(a[1], b[1]))
    union = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - intersection
    return intersection / union if union else 0


def coverage(results):
    families = []
    for task, meta in VISION_TASKS.items():
        items = [r for r in results if r['task'] == task]
        done = bool(items) and all(r['status'] in ('succeeded', 'not_applicable') and not r.get('truncated') for r in items)
        families.append({'task': task, 'label': meta[0], 'completed': done,
                         'instances': len(items), 'succeeded': sum(r['status'] == 'succeeded' for r in items),
                         'reason_codes': sorted({r['reason_code'] for r in items if r.get('reason_code')})})
    return {'task_families_total': len(VISION_TASKS), 'task_families_completed': sum(f['completed'] for f in families),
            'instances_planned': len(results), 'instances_completed': sum(r['status'] == 'succeeded' for r in results), 'families': families}


def report(results, status):
    lines = ['# Full Analysis', f'Estado: {status}', '']
    for r in results:
        lines += [f"## {VISION_TASKS[r['task']][0]} · {r['step_id']}", f"Estado: {r['status']}",
                  r.get('text') or r.get('reason_code') or 'Nenhum resultado detectado.', '']
    return '\n'.join(lines)
