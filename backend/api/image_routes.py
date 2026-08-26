"""
Endpoints de visão (Florence-2): descrição de imagem e OCR com regiões.

## Por que síncrono, se todo o resto do sistema é assíncrono

O contrato pedido é "manda a imagem, recebe a descrição": um `job_id` e dois
polls seriam outro produto. Mas o modelo **não** roda neste processo. A API
continua fazendo o que faz em todas as outras rotas — validar, persistir e
enfileirar — e apenas *espera* o resultado com um prazo:

  - o modelo no processo da API bloquearia o event loop por segundos, seria
    multiplicado por `api_workers`, e tornaria o torch uma dependência dura da
    API exatamente quando o empacotamento está tornando o torch opcional;
  - a espera **não** usa `AsyncResult.get()`, que é um poll bloqueante do
    Kombu: o laço abaixo usa `ready()` (um GET no Redis) com
    `await asyncio.sleep`, deixando o event loop livre;
  - as tasks vão para uma fila dedicada (`settings.vision_queue`), servida por
    um worker de concorrência 1. Na fila compartilhada, uma requisição de 60s
    ficaria atrás de conversões de PDF de vários minutos e daria 504 por
    motivos que não têm nada a ver com visão.

## O 504 não perde trabalho

Antes de despachar, a rota cria um job de verdade (Redis + MySQL, dono
incluído) do mesmo jeito que `/transcribe`. `vision_task_timeout_seconds`
(120s) é o dobro de `vision_request_timeout_seconds` (60s) de propósito: a task
sobrevive à requisição, então o 504 carrega `job_id`, `poll_url` e
`result_url`, e o chamador cai no contrato de polling que todas as outras
operações já usam. A task **não** é revogada no timeout.

## Autorização

Nada aqui é anônimo. `get_current_active_user` já aceita tanto um Bearer JWT
quanto `X-API-Key`, e é a mesma dependência usada por `/upload` e
`/transcribe`. As rotas não são endereçadas por `job_id`, então nada de
`api/deps.py` se aplica — a posse é *escrita* aqui, antes do despacho, o que é
o que faz `/jobs/{job_id}` e `/jobs/{job_id}/result` funcionarem depois sem
nenhum caso especial.
"""

import asyncio
import base64
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from shared.auth import get_current_active_user
from shared.config import get_settings
from shared.database import get_db
from shared.minio_client import get_minio_client
from shared.models import Job, JobStatus as DBJobStatus, User
from shared.redis_client import get_redis_client
from shared.schemas import (
    DEFAULT_VISION_CAPTION_TASK,
    VISION_CAPTION_TASKS,
    ImageDescribeRequest,
    ImageDescribeResponse,
    ImageOcrRequest,
    ImageOcrResponse,
    OcrLine,
    VisionCapabilitiesResponse,
    VisionModelInfo,
)
from shared.utils import calculate_file_checksum
# As regras de entrada de imagem (decode, limite de tamanho, magic bytes) moram
# em `workers/vision/image_input.py` e em lugar nenhum mais. Importar daqui é de
# graça: aquele módulo puxa apenas base64/re e os erros tipados de visão — nada
# de torch, transformers ou PIL (garantido por `test_vision_import_safety.py`).
from workers.vision.errors import VisionError
from workers.vision.image_input import (
    decode_base64_image,
    ensure_within_size_limit,
    extension_for_mime,
    sniff_image_mime,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/images", tags=["Vision"])
settings = get_settings()


# Uma flag só cobre `/images/describe` e `/images/ocr`: é um modelo atrás de um
# carregador, e duas flags permitiriam um estado que não existe.
VISION_DISABLED_MESSAGE = (
    "Image description is currently disabled "
    "(set ENABLE_IMAGE_DESCRIPTION=true to enable)"
)

# Quanto a rota de capacidades espera pelo worker. Curto de propósito: é uma
# sonda de ops, não uma inferência.
CAPABILITIES_WAIT_SECONDS = 10

# Intervalo entre dois `ready()`. Cada iteração é um GET no Redis; 250ms é
# barato o suficiente para não aparecer no perfil e curto o suficiente para não
# somar latência perceptível ao final da inferência.
POLL_INTERVAL_SECONDS = 0.25

SUPPORTED_IMAGE_FORMATS = "PNG, JPEG, WEBP, BMP, GIF, TIFF"


# ============================================
# Erros
# ============================================

def _error(
    status_code: int,
    error_code: str,
    message: str,
    job_id: Optional[str] = None,
    **extra: Any,
) -> HTTPException:
    """
    Todo corpo não-2xx daqui é `{"detail": {"error_code", "message", "job_id"}}`.

    O `error_code` existe para o cliente ramificar sem casar string de mensagem,
    e `job_id` é o que transforma um 504 em "continue pelo polling" em vez de
    "o trabalho evaporou".
    """
    detail: Dict[str, Any] = {
        "error_code": error_code,
        "message": message,
        "job_id": job_id,
    }
    detail.update(extra)
    return HTTPException(status_code=status_code, detail=detail)


def _require_vision_enabled() -> None:
    if not settings.enable_image_description:
        raise _error(503, "VISION_DISABLED", VISION_DISABLED_MESSAGE)


# ============================================
# Validação da imagem
# ============================================

def _as_http_error(exc: VisionError) -> HTTPException:
    """
    Fronteira entre o erro tipado de visão e o envelope HTTP desta rota.

    Cada `VisionError` já carrega o seu `error_code` e o seu `http_status`; aqui
    eles só viram `HTTPException`. Nenhuma regra é reimplementada — é o que
    permite que `workers/vision/image_input.py` seja a única implementação de
    decode/tamanho/formato, usada igualmente pela rota JSON, pela multipart e
    por quem mais precisar validar bytes de imagem.
    """
    return _error(exc.http_status, exc.error_code, str(exc))


def _decode_base64_image(payload: str) -> bytes:
    """Decode do corpo JSON. A regra é de `image_input`; aqui só o status HTTP.

    Tolera o prefixo `data:...;base64,` que todo `canvas.toDataURL()` produz e
    as quebras de linha que `base64 arquivo.png`, `base64.encodebytes()`,
    `openssl base64` e `Base64.getMimeEncoder()` inserem a cada 64/76 colunas.
    """
    try:
        return decode_base64_image(payload)
    except VisionError as exc:
        raise _as_http_error(exc)


def _validate_image_bytes(image_bytes: bytes) -> str:
    """
    Tamanho e formato, nesta ordem. Devolve o mime detectado.

    O limite é o de imagem (`vision_max_image_size_mb`, 10MB), nunca o de
    upload de documento (50MB): o custo aqui é de inferência, não de disco.
    """
    try:
        ensure_within_size_limit(image_bytes, settings.vision_max_image_size_mb)
        return sniff_image_mime(image_bytes)
    except VisionError as exc:
        raise _as_http_error(exc)


def _safe_filename(filename: Optional[str], mime: str) -> str:
    """
    Nome de arquivo seguro para o disco e para o MinIO.

    `filename` vem do chamador (campo JSON ou nome do multipart), então
    `Path(...).name` é obrigatório: sem ele, `../../etc/cron.d/x` viraria um
    caminho de escrita real dentro do worker.
    """
    candidate = Path(filename or "").name.strip() if filename else ""
    if not candidate or candidate in {".", ".."}:
        candidate = f"image{extension_for_mime(mime)}"
    return candidate[:200]


# ============================================
# Despacho para o worker de visão (seams de teste)
# ============================================

def _dispatch_vision_task(kind: str, **kwargs: Any):
    """
    Enfileira a task de visão e devolve o `AsyncResult`.

    Importa `workers.vision_tasks` aqui dentro, como `/transcribe` faz com
    `workers.tasks`: a imagem da API não precisa das dependências do worker, e
    a ausência delas tem que virar um 503 legível, não um ImportError no boot.
    O roteamento para `settings.vision_queue` vem de `task_routes` no
    `celery_app`, não daqui.
    """
    from workers.vision_tasks import describe_image_task, ocr_image_task

    task = {"describe": describe_image_task, "ocr": ocr_image_task}[kind]
    return task.delay(**kwargs)


def _dispatch_capabilities_task():
    """Enfileira a sonda de capacidades e devolve o `AsyncResult`."""
    from workers.vision_tasks import vision_capabilities_task

    return vision_capabilities_task.delay()


async def _wait_for_result(async_result, timeout_seconds: float) -> Optional[Any]:
    """
    Espera o resultado sem bloquear o event loop.

    `ready()` é um GET rápido no backend de resultado; o `await asyncio.sleep`
    entre os polls é o que deixa a API continuar servindo `/health` e
    `/jobs/*`. Um `AsyncResult.get()` aqui bloquearia o loop inteiro, e um
    `run_in_threadpool` colocaria estas requisições disputando o pool de 40
    threads do anyio com todas as outras dependências bloqueantes.

    Devolve `None` quando o prazo estoura — o chamador decide o que isso
    significa (504 na inferência, degradação em capacidades).
    """
    deadline = time.monotonic() + timeout_seconds
    while not async_result.ready():
        if time.monotonic() >= deadline:
            return None
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
    return async_result.result


# ============================================
# Job (Redis + MySQL) e persistência da imagem
# ============================================

def _create_vision_job(
    job_id: str,
    filename: str,
    mime: str,
    image_bytes: bytes,
    checksum: str,
    current_user: User,
    db: Session,
) -> Optional[Job]:
    """
    Cria o job antes do despacho, exatamente como `/transcribe`.

    É isto que faz o 504 ser recuperável e o que faz `api/deps.get_owned_job`
    autorizar o job depois sem nenhuma alteração: a posse está no MySQL (fonte
    da verdade) e no Redis (cache). `Job.source_type` é texto livre
    (`String(50)`), então "image" não precisa de migração.
    """
    created_at = datetime.utcnow()

    redis_client = get_redis_client()
    redis_client.set_job_status(
        job_id=job_id,
        job_type="main",
        status="queued",
        progress=0,
        name=filename,
    )
    redis_client.set_job_owner(job_id, current_user.id)
    redis_client.add_job_to_user(current_user.id, job_id)

    db_job = Job(
        id=job_id,
        user_id=current_user.id,
        filename=filename,
        name=filename,
        source_type="image",
        file_size_bytes=len(image_bytes),
        mime_type=mime,
        file_checksum=checksum,
        status=DBJobStatus.PENDING,
        job_type="MAIN",
        created_at=created_at,
    )
    try:
        db.add(db_job)
        db.commit()
    except Exception as e:
        # Mesmo tratamento do resto do repositório: o MySQL fora do ar degrada
        # a listagem de jobs, não pode derrubar a requisição.
        logger.error(f"Error creating image job in MySQL: {e}", exc_info=True)
        db.rollback()
        return None

    return db_job


def _mark_job_failed(job_id: str, db: Session, db_job: Optional[Job], error: str) -> None:
    try:
        get_redis_client().set_job_status(
            job_id=job_id,
            job_type="main",
            status="failed",
            progress=0,
            error=error,
        )
    except Exception as e:  # pragma: no cover - Redis indisponível
        logger.warning(f"Não foi possível marcar o job {job_id} como falho no Redis: {e}")

    if db_job is None:
        return
    try:
        db_job.status = DBJobStatus.FAILED
        db_job.error_message = error
        db.commit()
    except Exception:
        db.rollback()


def _persist_image(job_id: str, filename: str, image_bytes: bytes, mime: str) -> Path:
    """
    Grava a imagem no MinIO (tolerando falha) e no disco compartilhado.

    Os bytes **não** viajam pelo broker: base64 nos kwargs da task colocaria
    ~13MB por requisição dentro de uma mensagem do Redis. O worker lê o
    caminho; o bind mount `./tmp:/tmp/ingestify` (presente no compose base e no
    de produção) é o que faz a passagem funcionar.
    """
    try:
        minio_client = get_minio_client()
        minio_client.upload_file(
            bucket_name=minio_client.bucket_uploads,
            object_name=f"images/{job_id}/{filename}",
            file_data=image_bytes,
            content_type=mime,
        )
    except Exception as e:
        # O MinIO aqui é retenção, não o caminho de dados: o worker lê do disco.
        logger.warning(f"Failed to upload image to MinIO for job {job_id}: {e}")

    temp_dir = Path(settings.temp_storage_path) / "images" / job_id
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / filename
    temp_path.write_bytes(image_bytes)
    return temp_path


# ============================================
# Leitura do resultado da task
# ============================================

def _model_info(payload: Dict[str, Any]) -> VisionModelInfo:
    """
    Qual modelo respondeu. O worker manda; a configuração é só o fallback para
    o caso de um worker mais antigo não mandar (não vale um 500).
    """
    raw = payload.get("model") or {}
    return VisionModelInfo(
        model_id=raw.get("model_id", settings.vision_model_id),
        revision=raw.get("revision", settings.vision_model_revision),
        device=raw.get("device", payload.get("device", "unknown")),
        dtype=raw.get("dtype", payload.get("dtype", "unknown")),
    )


def _unwrap_task_payload(payload: Any, job_id: str, required: tuple) -> Dict[str, Any]:
    """
    Traduz o resultado da task em payload de sucesso ou em HTTPException.

    As tasks **retornam** a falha (`{"ok": False, "error_code", "http_status",
    "detail"}`) em vez de levantar, porque uma exceção não sobrevive ao
    serializador JSON de resultado do Celery com o código intacto. Aqui esse
    dicionário vira o status e o código que o chamador vê — sem stack trace, e
    com a mensagem acionável que o worker escreveu.
    """
    if not isinstance(payload, dict):
        # `AsyncResult.result` de uma task que levantou é a própria exceção.
        logger.error(f"Vision task for job {job_id} failed: {payload!r}")
        raise _error(
            500,
            "VISION_INFERENCE_FAILED",
            "A inferência de visão falhou. Consulte os logs do worker de visão "
            f"e o job {job_id} para o erro completo.",
            job_id=job_id,
        )

    if payload.get("ok") is False:
        raise _error(
            int(payload.get("http_status", 503)),
            str(payload.get("error_code", "VISION_ERROR")),
            str(payload.get("detail", "A inferência de visão falhou.")),
            job_id=job_id,
        )

    missing = [key for key in required if key not in payload]
    if missing:
        logger.error(
            f"Vision task for job {job_id} returned an unexpected payload "
            f"(missing {missing}): {sorted(payload)}"
        )
        raise _error(
            500,
            "VISION_INFERENCE_FAILED",
            f"O worker de visão devolveu um resultado incompleto (faltando: "
            f"{', '.join(missing)}).",
            job_id=job_id,
        )

    return payload


# ============================================
# Caminho comum das quatro rotas de inferência
# ============================================

async def _run_vision(
    kind: str,
    image_bytes: bytes,
    filename: Optional[str],
    task: Optional[str],
    current_user: User,
    db: Session,
) -> Dict[str, Any]:
    """
    Valida, cria o job, despacha e espera — para os quatro pontos de entrada.

    As rotas JSON e multipart delegam para cá justamente para não poderem
    divergir: uma correção de validação vale para as duas por construção.
    Devolve os campos comuns da resposta; cada rota acrescenta os seus.
    """
    mime = _validate_image_bytes(image_bytes)
    safe_name = _safe_filename(filename, mime)
    checksum = calculate_file_checksum(image_bytes)

    job_id = str(uuid4())
    db_job = _create_vision_job(
        job_id=job_id,
        filename=safe_name,
        mime=mime,
        image_bytes=image_bytes,
        checksum=checksum,
        current_user=current_user,
        db=db,
    )

    logger.info(
        f"VISION {kind.upper()} JOB created: {job_id} | user: {current_user.username} "
        f"| {safe_name} ({len(image_bytes)} bytes, {mime})"
    )

    try:
        image_path = _persist_image(job_id, safe_name, image_bytes, mime)
    except OSError as e:
        logger.error(f"Failed to persist image for job {job_id}: {e}", exc_info=True)
        _mark_job_failed(job_id, db, db_job, str(e))
        raise _error(
            500,
            "VISION_INFERENCE_FAILED",
            f"Não foi possível gravar a imagem para processamento: {e}",
            job_id=job_id,
        )

    kwargs: Dict[str, Any] = {"job_id": job_id, "image_path": str(image_path)}
    if kind == "describe":
        kwargs["task"] = task or DEFAULT_VISION_CAPTION_TASK

    try:
        async_result = _dispatch_vision_task(kind, **kwargs)
    except ImportError as e:
        logger.error(f"Vision tasks not available: {e}")
        _mark_job_failed(job_id, db, db_job, "Celery workers não disponíveis")
        raise _error(
            503,
            "CELERY_UNAVAILABLE",
            "Sistema de processamento indisponível: as tasks de visão não puderam "
            "ser carregadas. Verifique se o worker de visão está instalado e rodando.",
            job_id=job_id,
        )
    except Exception as e:
        # kombu.exceptions.OperationalError (broker fora do ar) e afins.
        logger.error(f"Error enqueueing vision job {job_id}: {e}", exc_info=True)
        _mark_job_failed(job_id, db, db_job, str(e))
        raise _error(
            503,
            "CELERY_UNAVAILABLE",
            f"Não foi possível enfileirar o job de visão: {e}",
            job_id=job_id,
        )

    result = await _wait_for_result(async_result, settings.vision_request_timeout_seconds)

    if result is None:
        # A task NÃO é revogada: `vision_task_timeout_seconds` é o dobro deste
        # prazo justamente para que ela termine e o resultado seja buscável.
        logger.warning(
            f"Vision job {job_id} exceeded the {settings.vision_request_timeout_seconds}s "
            f"request budget; the task keeps running."
        )
        raise _error(
            504,
            "VISION_TIMEOUT",
            f"A descrição não ficou pronta em {settings.vision_request_timeout_seconds}s. "
            f"O job continua processando.",
            job_id=job_id,
            poll_url=f"/jobs/{job_id}",
            result_url=f"/jobs/{job_id}/result",
        )

    required = ("description",) if kind == "describe" else ("text",)
    payload = _unwrap_task_payload(result, job_id, required + ("width", "height"))

    return {
        "job_id": job_id,
        "status": "completed",
        "image_base64": base64.b64encode(image_bytes).decode("ascii"),
        "image_mime_type": mime,
        "image_bytes": len(image_bytes),
        "image_sha256": checksum,
        "width": payload["width"],
        "height": payload["height"],
        "model": _model_info(payload),
        "duration_ms": int(payload.get("duration_ms", 0)),
        "_payload": payload,
    }


def _describe_response(common: Dict[str, Any], requested_task: str) -> ImageDescribeResponse:
    payload = common.pop("_payload")
    return ImageDescribeResponse(
        description=payload["description"],
        task=payload.get("task", requested_task),
        **common,
    )


def _ocr_response(common: Dict[str, Any]) -> ImageOcrResponse:
    payload = common.pop("_payload")
    lines = [OcrLine(**line) for line in payload.get("lines", [])]
    return ImageOcrResponse(text=payload["text"], lines=lines, **common)


# ============================================
# Rotas
# ============================================

@router.post(
    "/describe",
    response_model=ImageDescribeResponse,
    summary="Descrever imagem (JSON base64)",
)
async def describe_image(
    request: ImageDescribeRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Descreve uma imagem enviada em base64 e devolve a mesma imagem de volta.

    ## Corpo
    - `image_base64`: bytes da imagem em base64 (o prefixo `data:image/...;base64,`
      é aceito e removido)
    - `filename`: nome opcional, usado no job e no storage
    - `task`: `<MORE_DETAILED_CAPTION>` (padrão), `<DETAILED_CAPTION>` ou `<CAPTION>`

    ## Retorno
    A descrição, os metadados da imagem e o eco de `image_base64` — os bytes
    exatos que você enviou, re-codificados, nunca uma re-compressão.

    ## Timeout
    Se a inferência passar de `VISION_REQUEST_TIMEOUT_SECONDS`, a resposta é
    504 com `job_id`/`poll_url`: a task continua e o resultado sai em
    `/jobs/{job_id}/result`.
    """
    _require_vision_enabled()

    image_bytes = _decode_base64_image(request.image_base64)
    common = await _run_vision(
        kind="describe",
        image_bytes=image_bytes,
        filename=request.filename,
        task=request.task,
        current_user=current_user,
        db=db,
    )
    return _describe_response(common, request.task)


@router.post(
    "/describe/upload",
    response_model=ImageDescribeResponse,
    summary="Descrever imagem (multipart)",
)
async def describe_image_upload(
    file: UploadFile = File(..., description="Imagem (PNG, JPEG, WEBP, BMP, GIF, TIFF)"),
    task: str = Form(
        DEFAULT_VISION_CAPTION_TASK,
        description="<MORE_DETAILED_CAPTION>, <DETAILED_CAPTION> ou <CAPTION>",
    ),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Igual a `POST /images/describe`, com a imagem em `multipart/form-data`.

    Existe como caminho irmão porque o FastAPI não hospeda um corpo JSON e
    parâmetros `File`/`Form` na mesma operação — e sniffar o content-type
    produziria uma única operação ilegível no OpenAPI.
    """
    _require_vision_enabled()

    # O multipart não passa pelo `Literal` do modelo JSON, então a mesma
    # restrição é aplicada à mão — senão este caminho aceitaria um prompt
    # arbitrário que o caminho JSON recusa.
    if task not in VISION_CAPTION_TASKS:
        raise _error(
            422,
            "UNSUPPORTED_CAPTION_TASK",
            f"task inválido: {task}. Aceitos: <MORE_DETAILED_CAPTION>, "
            f"<DETAILED_CAPTION>, <CAPTION>.",
        )

    image_bytes = await file.read()
    common = await _run_vision(
        kind="describe",
        image_bytes=image_bytes,
        filename=file.filename,
        task=task,
        current_user=current_user,
        db=db,
    )
    return _describe_response(common, task)


@router.post("/ocr", response_model=ImageOcrResponse, summary="OCR de imagem (JSON base64)")
async def ocr_image(
    request: ImageOcrRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Extrai o texto de uma imagem com `<OCR_WITH_REGION>` do Florence-2.

    Devolve o texto completo e, por linha, o quadrilátero detectado
    (`quad_box`, 8 valores) e o retângulo derivado (`bbox`, 4 valores), em
    pixels absolutos da imagem original.

    Uma imagem sem texto detectável é 200 com `text: ""` e `lines: []` — nunca
    um 4xx.
    """
    _require_vision_enabled()

    image_bytes = _decode_base64_image(request.image_base64)
    common = await _run_vision(
        kind="ocr",
        image_bytes=image_bytes,
        filename=request.filename,
        task=None,
        current_user=current_user,
        db=db,
    )
    return _ocr_response(common)


@router.post("/ocr/upload", response_model=ImageOcrResponse, summary="OCR de imagem (multipart)")
async def ocr_image_upload(
    file: UploadFile = File(..., description="Imagem (PNG, JPEG, WEBP, BMP, GIF, TIFF)"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Igual a `POST /images/ocr`, com a imagem em `multipart/form-data`."""
    _require_vision_enabled()

    image_bytes = await file.read()
    common = await _run_vision(
        kind="ocr",
        image_bytes=image_bytes,
        filename=file.filename,
        task=None,
        current_user=current_user,
        db=db,
    )
    return _ocr_response(common)


@router.get(
    "/capabilities",
    response_model=VisionCapabilitiesResponse,
    summary="Estado do subsistema de visão",
)
async def vision_capabilities(
    current_user: User = Depends(get_current_active_user),
):
    """
    O que o worker de visão consegue fazer *neste* deploy.

    A resposta vem do worker, não da API: a única resposta que vale alguma
    coisa descreve o processo que de fato carrega o modelo, e calcular isso
    aqui obrigaria a API a importar torch.

    Se nenhum worker responder em 10s, isto ainda é 200 — com
    `dependencies_installed=false` e `reason` preenchido. Uma sonda de ops não
    pode dar 5xx quando aquilo que ela sonda está fora do ar.
    """
    _require_vision_enabled()

    # Só o que a API sabe sem importar torch; o worker sobrescreve o resto.
    degraded = VisionCapabilitiesResponse(
        enabled=True,
        provider=settings.vision_provider,
        model_id=settings.vision_model_id,
        revision=settings.vision_model_revision,
        device_requested=settings.device,
        device_resolved="unknown",
        torch_available=False,
        cuda_available=False,
        cuda_device_name=None,
        dependencies_installed=False,
        model_downloaded=False,
        model_loaded=False,
        trust_remote_code=settings.vision_trust_remote_code,
        reason="no vision worker responded within 10s",
    )

    try:
        async_result = _dispatch_capabilities_task()
    except Exception as e:
        logger.warning(f"Could not dispatch vision capabilities probe: {e}")
        return degraded.model_copy(update={"reason": f"could not reach the broker: {e}"})

    result = await _wait_for_result(async_result, CAPABILITIES_WAIT_SECONDS)
    if not isinstance(result, dict):
        if result is not None:
            logger.warning(f"Vision capabilities probe failed: {result!r}")
        return degraded

    merged = degraded.model_dump()
    merged.update({k: v for k, v in result.items() if k in merged})
    merged["enabled"] = True
    # O worker respondeu: o `reason` de degradação não vale mais, e um worker
    # saudável simplesmente não manda `reason`.
    merged["reason"] = result.get("reason")
    return VisionCapabilitiesResponse(**merged)
