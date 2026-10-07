"""Typed facial contracts and bounded planning; no native runtime imports."""
import json
import math
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

FACIAL_TASKS = {
    'face_detection': 'Detecção facial',
    'face_movements': 'Movimentos faciais',
    'face_expression_classification': 'Expressão estimada',
}
FaceOperation = Literal['face_detection', 'face_movements', 'face_expression_classification']
StepStatus = Literal['pending', 'running', 'succeeded', 'failed', 'skipped', 'not_applicable']


class FaceOptions(BaseModel):
    model_config = ConfigDict(extra='forbid')
    mode: Literal['detection', 'expressions'] = 'expressions'
    max_faces: int = Field(5, ge=1, le=10, strict=True)
    min_detection_confidence: float = Field(.5, ge=0, le=1, allow_inf_nan=False)
    min_suppression_threshold: float = Field(.3, ge=0, le=1, allow_inf_nan=False)
    min_face_presence_confidence: float = Field(.5, ge=0, le=1, allow_inf_nan=False)
    min_expression_score: float = Field(.5, ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode='after')
    def expression_fields(self):
        if self.mode == 'detection' and self.model_fields_set & {'min_face_presence_confidence', 'min_expression_score'}:
            raise ValueError('Parâmetros de expressão exigem mode=expressions')
        return self

    def effective(self):
        value = self.model_dump()
        if self.mode == 'detection':
            for key in ('min_face_presence_confidence', 'min_expression_score'):
                value.pop(key)
        return value


class FaceRequestOptions(FaceOptions):
    deadline_seconds: int = Field(300, ge=1, le=300, strict=True)


class FullFaceOptions(FaceOptions):
    mode: Literal['expressions'] = 'expressions'
    max_faces: int = Field(5, ge=1, le=5, strict=True)


class FaceModelInfo(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    operation: str
    provider: str
    model_id: str
    revision: str
    sha256: str
    runtime: str
    runtime_version: str
    device: Literal['cpu'] = 'cpu'
    license: str
    license_url: str
    additional_license_urls: list[str] = Field(default_factory=list)
    source_url: str
    preprocessing: dict = Field(default_factory=dict)
    labels: list[str] = Field(default_factory=list)


class FaceStepResult(BaseModel):
    kind: Literal['face'] = 'face'
    step_id: str
    operation: FaceOperation
    face_id: str | None = None
    input: dict = Field(default_factory=dict)
    status: StepStatus
    reason_code: str | None = None
    output: dict = Field(default_factory=dict)
    attempts: int = 0
    duration_ms: int = 0
    truncated: bool = False


class FaceRecord(BaseModel):
    face_id: str
    bbox: list[float] = Field(min_length=4, max_length=4)
    bbox_normalized: list[float] = Field(min_length=4, max_length=4)
    detection_confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    keypoints: list[dict] = Field(default_factory=list)
    crop: list[int] = Field(min_length=4, max_length=4)
    movements: dict = Field(default_factory=dict)
    expression: dict = Field(default_factory=dict)


class FacialBlock(BaseModel):
    detection: dict
    faces: list[FaceRecord] = Field(default_factory=list)
    models: list[FaceModelInfo] = Field(default_factory=list)
    request: dict
    coverage: dict
    steps: list[FaceStepResult]


class FaceAnalysisResult(FacialBlock):
    operation: Literal['face_analysis'] = 'face_analysis'
    schema_version: Literal['face-result-v1'] = 'face-result-v1'
    profile: Literal['image-faces-v1'] = 'image-faces-v1'
    analysis_status: Literal['completed', 'partial', 'failed', 'cancelled']
    width: int
    height: int
    image_base64: str | None = None
    image_mime_type: str = 'image/png'
    duration_ms: int = 0
    calls_started: int = 0
    calls_by_provider: dict[str, int] = Field(default_factory=dict)
    reason_code: str | None = None
    source_sha256: str = ''
    frame_policy: str = 'first_frame'


def manifest():
    return json.loads(Path(__file__).with_name('face_models.json').read_text())


def profile(configuration):
    if configuration.get('mode') == 'faces':
        return 'image-faces-v1'
    return configuration.get('full_options', {}).get('profile', 'image-full-v1')


def face_options(configuration):
    return configuration['face_options'] if profile(configuration) == 'image-faces-v1' else configuration['full_options']['faces']


def facial_step(operation, face=None, status='pending', reason=None):
    return {'step_id': operation + ('-' + face['face_id'] if face else ''),
            'task': operation, 'kind': 'face', 'provider': provider(operation),
            'face_id': face['face_id'] if face else None, 'input': {'face': face} if face else {},
            'status': status, 'reason_code': reason}


def provider(task):
    if task == 'face_expression_classification':
        return 'emotiefflib'
    return 'mediapipe' if task in FACIAL_TASKS else 'florence'


def initial_steps(configuration):
    from shared.image_full import initial_steps as florence_steps
    selected = profile(configuration)
    return ([facial_step('face_detection')] if selected != 'image-full-v1' else []) + (
        florence_steps() if selected != 'image-faces-v1' else [])


def call_limits(configuration):
    selected = profile(configuration)
    if selected == 'image-full-v1':
        return {'florence': 32, 'face': 0, 'total': 32}
    options = face_options(configuration)
    facial = 2 * (1 + (2 * options['max_faces'] if options['mode'] == 'expressions' else 0))
    florence = 32 if selected == 'image-full-v2' else 0
    return {'florence': florence, 'face': facial, 'total': florence + facial}


def dependent_steps(detection, options):
    if options['mode'] != 'expressions':
        return []
    faces = detection.get('output', {}).get('faces', []) if detection['status'] == 'succeeded' else []
    if not faces:
        good = detection['status'] == 'succeeded'
        return [facial_step(task, status='not_applicable' if good else 'skipped',
                            reason='no_faces' if good else 'dependency_failed') for task in list(FACIAL_TASKS)[1:]]
    return [facial_step(task, face) for face in faces for task in list(FACIAL_TASKS)[1:]]


def select_faces(detections, options, width, height):
    valid = []
    for candidate in detections:
        box, score = candidate['bbox'], candidate['detection_confidence']
        if len(box) != 4 or not all(math.isfinite(x) for x in [*box, score]):
            raise ValueError('Non-finite detector output')
        box = [max(0., min(float(x), width if i % 2 == 0 else height)) for i, x in enumerate(box)]
        if box[0] < box[2] and box[1] < box[3] and 1 >= score >= options['min_detection_confidence']:
            valid.append({**candidate, 'bbox': box})
    valid.sort(key=lambda f: (-f['detection_confidence'], -(f['bbox'][2]-f['bbox'][0])*(f['bbox'][3]-f['bbox'][1]), *f['bbox']))
    selected = []
    for index, item in enumerate(valid[:options['max_faces']]):
        box = item['bbox']
        dx, dy = (box[2]-box[0])*.25, (box[3]-box[1])*.25
        crop = [max(0, math.floor(box[0]-dx)), max(0, math.floor(box[1]-dy)),
                min(width, math.ceil(box[2]+dx)), min(height, math.ceil(box[3]+dy))]
        selected.append({**item, 'face_id': f'face-{index+1:03d}', 'crop': crop,
                         'bbox_normalized': [x/(width if i % 2 == 0 else height) for i, x in enumerate(box)]})
    omitted = len(valid)-len(selected)
    return {'faces': selected, 'detected_count': len(valid), 'selected_count': len(selected),
            'omitted_count': omitted, 'selection_limited': bool(omitted), 'omission_reason': 'max_faces' if omitted else None}


def step_result(item):
    return {**item, 'kind': 'face', 'operation': item['task'], 'face_id': item.get('face_id') or item.get('input', {}).get('face', {}).get('face_id')}


def block(results, configuration):
    options = face_options(configuration)
    facial = [step_result(r) for r in results if r['task'] in FACIAL_TASKS]
    detection = next((r for r in facial if r['operation'] == 'face_detection'),
                     {'status': 'skipped', 'reason_code': 'dependency_failed', 'output': {}})
    faces = []
    for raw in detection.get('output', {}).get('faces', []):
        face = dict(raw)
        for task, field in [('face_movements', 'movements'), ('face_expression_classification', 'expression')]:
            found = next((r for r in facial if r['operation'] == task and r.get('face_id') == face['face_id']), None)
            face[field] = {'status': found['status'], 'reason_code': found.get('reason_code'), **found.get('output', {})} if found else {'status': 'not_applicable', 'reason_code': 'not_requested'}
        faces.append(face)
    families = []
    for task, label in FACIAL_TASKS.items():
        requested = task == 'face_detection' or options['mode'] == 'expressions'
        steps = [r for r in facial if r['operation'] == task]
        done = bool(steps) and all(r['status'] in ('succeeded', 'not_applicable') for r in steps)
        families.append({'task': task, 'label': label, 'requested': requested, 'completed': requested and done,
                         'instances': len(steps), 'succeeded': sum(r['status'] == 'succeeded' for r in steps),
                         'reason_codes': sorted({r['reason_code'] for r in steps if r.get('reason_code')}) if requested else ['not_requested']})
    return {'request': options, 'models': configuration.get('face_models', []),
            'detection': {**{k: v for k, v in detection.get('output', {}).items() if k != 'faces'},
                          'status': detection['status'], 'reason_code': detection.get('reason_code')},
            'faces': faces, 'steps': facial, 'coverage': {
                'task_families_total': sum(f['requested'] for f in families),
                'task_families_completed': sum(f['completed'] for f in families), 'families': families}}


def markdown(facial):
    lines = ['## Rostos e expressões', '', 'Estimativa de expressão visível; não determina o estado emocional.', '']
    detection = facial['detection']
    lines.append(f"Detecção: {detection['status']}; selecionados: {detection.get('selected_count', 0)}; omitidos: {detection.get('omitted_count', 0)}.")
    for face in facial['faces']:
        expression = face['expression']
        lines += ['', f"### {face['face_id']}", f"Caixa (pixels): {face['bbox']}",
                  f"Movimentos: {face['movements']['status']}",
                  f"Expressão: {expression.get('label') or expression.get('decision') or expression['status']}"]
        for item in expression.get('scores', []):
            lines.append(f"- {item['label']}: {item['score']:.4f}")
    return '\n'.join(lines)
