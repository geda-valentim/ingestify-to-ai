"""Dedicated facial APIs reuse the durable image submission contract."""
import json
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session
from shared.config import get_settings
from shared.database import get_db
from shared.models import User
from shared.schemas import FACE_PURGE_SOURCE_DESCRIPTION, FaceAnalyzeRequest, FaceAnalyzeResponse, ImageFullQueuedResponse
from shared.face_analysis import FaceOptions, FaceRequestOptions, FullFaceOptions
from api.iam_deps import require

router = APIRouter(prefix='/images/faces', tags=['Vision'])


def face_capabilities():
    from api.image_routes import _read_capabilities_heartbeat
    settings = get_settings()
    try:
        heartbeat = _read_capabilities_heartbeat() or {}
    except Exception:
        heartbeat = {}
    native = heartbeat.get('faces', {}) if settings.face_analysis_enabled else {}
    return {**native, 'enabled': settings.face_analysis_enabled,
            'ready': bool(settings.face_analysis_enabled and native.get('ready')),
            'reason': None if native.get('ready') and settings.face_analysis_enabled else ('disabled' if not settings.face_analysis_enabled else 'worker_unavailable'),
            'stages': native.get('stages', {}), 'models': native.get('models', []),
            'options_schema': FaceRequestOptions.model_json_schema(),
            'full_options_schema': FullFaceOptions.model_json_schema(),
            'defaults': FaceRequestOptions().effective(), 'max_image_size_mb': settings.vision_max_image_size_mb,
            'max_image_pixels': settings.vision_max_image_pixels}


def require_faces(mode):
    capabilities = face_capabilities()
    tasks = ['face_detection'] + (['face_movements', 'face_expression_classification'] if mode == 'expressions' else [])
    if not capabilities['enabled'] or not all(capabilities['stages'].get(task, {}).get('ready') for task in tasks):
        raise HTTPException(503, {'error_code': 'FACE_UNAVAILABLE', 'message': 'As etapas faciais solicitadas não estão disponíveis',
                                  'stages': capabilities['stages']})
    return capabilities


@router.get('/capabilities', summary="Modelos, parâmetros e prontidão da análise facial")
def capabilities(user: User = Depends(require("images.analyze"))):
    return face_capabilities()


@router.post('', response_model=FaceAnalyzeResponse | ImageFullQueuedResponse, status_code=202,
             summary="Detectar rostos e expressões (JSON base64)")
async def analyze(request: FaceAnalyzeRequest, http_request: Request,
                  user: User = Depends(require("images.analyze")), db: Session = Depends(get_db),
                  idempotency_key: str = Header(..., min_length=1, max_length=128)):
    from api.image_routes import _decode_base64_image, _plan_location, _json_location, parse_tags_or_422
    from api.image_full_routes import run_full
    plan = _plan_location(db, user, http_request, _json_location(request))
    return await run_full(request, http_request, _decode_base64_image(request.image_base64), request.filename,
                          user, db, parse_tags_or_422(request.tags), plan)


@router.post('/upload', response_model=FaceAnalyzeResponse | ImageFullQueuedResponse, status_code=202,
             summary="Detectar rostos e expressões (multipart)")
async def upload(http_request: Request, file: UploadFile = File(...), face_options: str | None = Form(None),
                 wait: bool = Form(False), project: str | None = Form(None), project_id: str | None = Form(None),
                 folder: str | None = Form(None), folder_id: str | None = Form(None), tags: str | None = Form(None),
                 datalake: str | None = Form(None),
                 purge_source: bool = Form(False, description=FACE_PURGE_SOURCE_DESCRIPTION),
                 idempotency_key: str = Header(..., min_length=1, max_length=128),
                 user: User = Depends(require("images.analyze")), db: Session = Depends(get_db)):
    from api.image_routes import _plan_location, _json_location
    from api.image_full_routes import run_full
    from shared.tags import parse_tags
    from pydantic import ValidationError
    fields = await http_request.form()
    allowed = {'file', 'face_options', 'wait', 'project', 'project_id', 'folder', 'folder_id', 'tags', 'datalake', 'purge_source'}
    if set(fields)-allowed or any(len(fields.getlist(name)) != 1 for name in fields):
        raise HTTPException(422, 'Campos desconhecidos ou repetidos no upload facial')
    try:
        request = FaceAnalyzeRequest(image_base64='multipart', filename=file.filename,
            project=project, project_id=project_id, folder=folder, folder_id=folder_id, wait=wait,
            purge_source=purge_source,
            face_options=json.loads(face_options) if face_options else {}, datalake=json.loads(datalake) if datalake else None)
        parsed_tags = parse_tags(tags)
    except (ValueError, TypeError, ValidationError) as exc:
        raise HTTPException(422, 'Imagem/opções/tags inválidas') from exc
    plan = _plan_location(db, user, http_request, _json_location(request))
    return await run_full(request, http_request, await file.read(get_settings().vision_max_image_size_mb * 1024 * 1024 + 1), file.filename, user, db, parsed_tags, plan)
