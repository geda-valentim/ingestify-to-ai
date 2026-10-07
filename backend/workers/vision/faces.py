"""Local, checksum-pinned MediaPipe and EmotiEffLib ONNX adapters."""
import hashlib
import importlib.metadata
import importlib.util
import math
import time
from functools import lru_cache
from pathlib import Path
from shared.face_analysis import manifest, FaceModelInfo, select_faces


class FaceFailure(RuntimeError):
    def __init__(self, code):
        self.error_code = code
        super().__init__(code)


@lru_cache(maxsize=32)
def _checksum(path, size, modified):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@lru_cache(maxsize=4)
def runtime_usable(runtime):
    try:
        if runtime == 'mediapipe':
            from mediapipe.tasks.python.core.mediapipe_c_bindings import load_raw_library
            load_raw_library()
        else:
            import onnxruntime
            import cv2
        return True
    except (ImportError, OSError):
        return False


def capabilities():
    from shared.config import get_settings
    settings = get_settings()
    stages, models = {}, []
    for entry in manifest()['models']:
        reason = None
        if not settings.face_analysis_enabled:
            reason = 'disabled'
        elif not importlib.util.find_spec(entry['runtime']) or (entry['runtime'] == 'onnxruntime' and not importlib.util.find_spec('cv2')):
            reason = 'dependency_missing'
        else:
            try:
                if importlib.metadata.version(entry['runtime']) != entry['runtime_version']:
                    reason = 'runtime_version_mismatch'
                elif not runtime_usable(entry['runtime']):
                    reason = 'dependency_unusable'
                path = Path(settings.face_model_cache_dir) / entry['filename']
                if not path.is_file():
                    reason = reason or 'weights_missing'
                else:
                    stat = path.stat()
                    if _checksum(str(path), stat.st_size, stat.st_mtime_ns) != entry['sha256']:
                        reason = reason or 'weights_checksum_mismatch'
            except OSError:
                reason = 'weights_unavailable'
        models.append(FaceModelInfo.model_validate(entry).model_dump())
        stages[entry['operation']] = {'ready': reason is None, 'reason': reason}
    return {'enabled': settings.face_analysis_enabled, 'ready': all(s['ready'] for s in stages.values()),
            'stages': stages, 'models': models}


class FacePipeline:
    def __init__(self, options, expected_models):
        from shared.config import get_settings
        self.options = options
        available = capabilities()
        required = ['face_detection'] + (['face_movements', 'face_expression_classification'] if options['mode'] == 'expressions' else [])
        if not all(available['stages'][task]['ready'] for task in required):
            raise FaceFailure('face_provider_unavailable')
        if available['models'] != expected_models:
            raise FaceFailure('face_model_configuration_changed')
        self.root = Path(get_settings().face_model_cache_dir)
        self.entries = {m['operation']: m for m in manifest()['models']}
        self.detector = self.landmarker = self.classifier = None

    def _image(self, bitmap):
        import mediapipe as mp
        import numpy as np
        return mp.Image(image_format=mp.ImageFormat.SRGB, data=np.asarray(bitmap).copy())

    def detection(self, bitmap):
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision
        if self.detector is None:
            self.detector = vision.FaceDetector.create_from_options(vision.FaceDetectorOptions(
                base_options=python.BaseOptions(model_asset_path=str(self.root / self.entries['face_detection']['filename'])),
                running_mode=vision.RunningMode.IMAGE,
                min_detection_confidence=self.options['min_detection_confidence'],
                min_suppression_threshold=self.options['min_suppression_threshold']))
        detected = self.detector.detect(self._image(bitmap))
        width, height = bitmap.size
        raw = []
        for item in detected.detections:
            box = item.bounding_box
            raw.append({'bbox': [box.origin_x, box.origin_y, box.origin_x+box.width, box.origin_y+box.height],
                        'detection_confidence': float(item.categories[0].score),
                        'keypoints': [{'index': i, 'x': p.x*width, 'y': p.y*height,
                                      'x_normalized': p.x, 'y_normalized': p.y} for i, p in enumerate(item.keypoints)]})
        result = select_faces(raw, self.options, width, height)
        # Preserve other detected nose positions to reject ambiguous associations,
        # including candidates excluded by the public face limit.
        for face in result['faces']:
            face['other_noses'] = [[f['keypoints'][2]['x'], f['keypoints'][2]['y']] for f in raw
                                   if f['keypoints'] != face['keypoints'] and len(f['keypoints']) > 2]
        return result

    def movements(self, bitmap, face):
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision
        if self.landmarker is None:
            self.landmarker = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
                base_options=python.BaseOptions(model_asset_path=str(self.root / self.entries['face_movements']['filename'])),
                running_mode=vision.RunningMode.IMAGE, num_faces=1, output_face_blendshapes=True,
                min_face_detection_confidence=.5,
                min_face_presence_confidence=self.options['min_face_presence_confidence']))
        crop = bitmap.crop(tuple(face['crop']))
        try:
            result = self.landmarker.detect(self._image(crop))
            if not result.face_landmarks:
                raise FaceFailure('face_landmarks_unavailable')
            points = result.face_landmarks[0]
            width, height = bitmap.size
            x1, y1, x2, y2 = face['crop']
            landmarks = [{'index': i, 'x': x1+p.x*(x2-x1), 'y': y1+p.y*(y2-y1),
                          'x_normalized': (x1+p.x*(x2-x1))/width,
                          'y_normalized': (y1+p.y*(y2-y1))/height,
                          'z': p.z, 'z_unit': 'crop_width_relative'} for i, p in enumerate(points)]
            nose = landmarks[1]
            target = face['keypoints'][2]
            distance = math.hypot(nose['x']-target['x'], nose['y']-target['y'])
            box = face['bbox']
            if distance > .35*math.hypot(box[2]-box[0], box[3]-box[1]) or any(
                    math.hypot(nose['x']-x, nose['y']-y) <= distance for x, y in face.get('other_noses', [])):
                raise FaceFailure('face_association_ambiguous')
            return {'landmarks': landmarks, 'landmark_count': len(landmarks),
                    'blendshapes': [{'name': c.category_name, 'score': float(c.score)} for c in result.face_blendshapes[0]]}
        finally:
            crop.close()

    def expression(self, bitmap, face):
        import cv2
        import numpy as np
        import onnxruntime as ort
        # This checkpoint uses detector crops, independently of the mesh.
        box = face['bbox']
        if any(box[0] <= x <= box[2] and box[1] <= y <= box[3] for x, y in face.get('other_noses', [])):
            raise FaceFailure('face_association_ambiguous')
        entry = self.entries['face_expression_classification']
        if self.classifier is None:
            settings = ort.SessionOptions()
            settings.intra_op_num_threads = 2
            settings.inter_op_num_threads = 1
            self.classifier = ort.InferenceSession(str(self.root / entry['filename']), sess_options=settings,
                                                   providers=['CPUExecutionProvider'])
        crop = bitmap.crop(tuple(box))
        try:
            data = cv2.resize(np.asarray(crop), (224, 224), interpolation=cv2.INTER_LINEAR) / 255.
            data = (data-np.asarray(entry['preprocessing']['mean']))/np.asarray(entry['preprocessing']['std'])
            data = data.transpose(2, 0, 1).astype('float32')[None, ...]
            logits = self.classifier.run(None, {self.classifier.get_inputs()[0].name: data})[0].reshape(-1)
            if len(logits) != len(entry['labels']) or not np.isfinite(logits).all():
                raise FaceFailure('expression_output_invalid')
            scores = np.exp(logits-logits.max())
            scores /= scores.sum()
            index = int(scores.argmax())
            conclusive = float(scores[index]) >= self.options['min_expression_score']
            return {'decision': 'estimated' if conclusive else 'inconclusive',
                    'label': entry['labels'][index] if conclusive else None,
                    'best_class': entry['labels'][index], 'score': float(scores[index]),
                    'scores': [{'label': label, 'score': float(score)} for label, score in zip(entry['labels'], scores)],
                    'score_kind': 'softmax', 'calibrated': False, 'threshold': self.options['min_expression_score']}
        finally:
            crop.close()

    def analyze(self, bitmap, item):
        started = time.monotonic()
        operation = item['task']
        if operation == 'face_detection':
            output = self.detection(bitmap)
        elif operation == 'face_movements':
            output = self.movements(bitmap, item['input']['face'])
        else:
            output = self.expression(bitmap, item['input']['face'])
        return {'output': output, 'duration_ms': round((time.monotonic()-started)*1000)}

    def close(self):
        for instance in (self.detector, self.landmarker):
            if instance:
                instance.close()
        self.classifier = None
