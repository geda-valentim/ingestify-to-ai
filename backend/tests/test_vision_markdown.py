"""
`output_format=markdown` of the image routes and `?format=` of their results.

The JSON stays the default and byte-identical; Markdown is a second rendering of
the same result (shared/vision_markdown.py), chosen per request and stored on the
job as the default of GET /jobs/{job_id}/result.
"""
from datetime import datetime

import pytest

from shared import vision_markdown as vm
from shared.models import Job
from shared.schemas import ImageAnalyzeResponse, ImageDescribeResponse, ImageOcrResponse
from shared.vision_results import vision_result

from tests.test_images_endpoints import (  # noqa: F401  (fixtures)
    DESCRIBE_PAYLOAD,
    MODEL_INFO,
    OCR_PAYLOAD,
    PNG_B64,
    PNG_BYTES,
    _png_upload,
    _post_json,
    _post_multipart,
    app,
    db,
    dispatch,
    install_dispatch,
    minio,
    no_redis,
    temp_storage,
    users,
)

ANALYZE_PAYLOAD = {
    "ok": True,
    "task": "<OD>",
    "text": "car\nperson",
    "output": {"bboxes": [[1, 2, 30.5, 40], [5, 6, 7, 8]], "labels": ["car", "person"]},
    "regions": [{"label": "car", "bbox": [1.0, 2.0, 30.5, 40.0], "polygons": []},
                {"label": "person", "bbox": [5.0, 6.0, 7.0, 8.0], "polygons": []}],
    "request": {"task": "<OD>"},
    "width": 64,
    "height": 48,
    "duration_ms": 10,
    "model": MODEL_INFO,
}

MARKDOWN = "text/markdown; charset=utf-8"


# ---------------------------------------------------------------------------
# Renderer (pure)
# ---------------------------------------------------------------------------

def test_describe_renders_heading_description_and_metadata():
    md = vm.render_describe({**DESCRIBE_PAYLOAD, "model": MODEL_INFO}, job_id="job-1", filename="foto.png")
    assert md == (
        "# Descrição da imagem\n\n"
        "Um quadrado azul de um pixel sobre fundo branco.\n\n"
        "## Metadados\n\n"
        "- Arquivo: foto.png\n"
        "- Dimensões: 1 × 1 px\n"
        f"- Modelo: `{MODEL_INFO['model_id']}` (revisão `{MODEL_INFO['revision']}`)\n"
        "- Tarefa: Descrição muito detalhada (`<MORE_DETAILED_CAPTION>`)\n"
        "- Job: `job-1`\n"
    )
    assert vm.render_describe({**DESCRIBE_PAYLOAD}, job_id="job-1") == vm.render_describe({**DESCRIBE_PAYLOAD}, job_id="job-1")


def test_model_text_cannot_inject_html_or_markdown_structure():
    hostile = ("<script>alert(1)</script> <!-- hide\n# Title\n- item\n1. first\n> quote\n"
               "[link](javascript:x) `code` *bold* _it_ | pipe\x07\n```\n~~~")
    md = vm.render_describe({"description": hostile, "task": "<CAPTION>"})
    body = md.split("\n\n")[1]
    assert "<script>" not in md and "<!--" not in md
    assert "&lt;script&gt;" in body
    lines = body.split("\n")
    assert lines[1] == "\\# Title" and lines[2] == "\\- item" and lines[3] == "1\\. first"
    assert lines[4].startswith("&gt; quote")
    assert "\\[link\\](javascript:x)" in body and "\\`code\\`" in body and "\\*bold\\*" in body
    assert "\\_it\\_" in body and "\\| pipe" in body and "\x07" not in body
    assert "\\`\\`\\`" in body and lines[-1] == "\\~~~"
    # identifiers stay in code spans, without the backticks that would close them
    assert "`a b`" in vm.render_describe({"description": "x"}, job_id="a`\nb")
    # a table cell stays one line
    assert vm.cell("a\nb|c") == "a b\\|c"


def test_ocr_keeps_one_line_per_detected_line():
    md = vm.render_ocr({**OCR_PAYLOAD}, job_id="job-2", filename="nf.png")
    assert md.startswith("# Texto da imagem\n\nINGESTIFY  \nnota fiscal\n\n## Metadados\n\n")
    assert "- Tarefa: Extrair texto com regiões (`<OCR_WITH_REGION>`)" in md


def test_empty_ocr_says_no_text():
    md = vm.render_ocr({"text": "", "lines": [], "width": 10, "height": 10})
    assert md.startswith("# Texto da imagem\n\nNenhum texto detectado.\n\n")


def test_analyze_renders_task_label_and_regions_table():
    md = vm.render_analyze({**ANALYZE_PAYLOAD}, job_id="job-3")
    assert md.startswith("# Detectar objetos\n\n## Regiões\n\n")  # text only repeats the labels
    assert ("| Rótulo | x_min | y_min | x_max | y_max |\n| --- | --- | --- | --- | --- |\n"
            "| car | 1 | 2 | 30.5 | 40 |\n| person | 5 | 6 | 7 | 8 |") in md
    caption = vm.render_analyze({"task": "<REGION_TO_DESCRIPTION>", "text": "a red | car",
                                 "regions": [], "request": {"task": "<REGION_TO_DESCRIPTION>",
                                                            "region": [0, 0.25, 0.5, 1]}})
    assert caption.startswith("# Descrever uma região\n\na red \\| car\n\n## Metadados")
    assert "- Região pedida (normalizada): 0, 0.25, 0.5, 1" in caption
    polygons = vm.render_analyze({"task": "<REFERRING_EXPRESSION_SEGMENTATION>", "text": "road",
                                  "regions": [{"label": "road", "polygons": [[1, 2, 3, 4, 5, 6]]}]})
    assert "1 região(ões) só com polígonos" in polygons and "| Rótulo |" not in polygons
    assert "Nenhum resultado detectado." in vm.render_analyze({"task": "<OD>", "text": "", "regions": []})


def _face(**changes):
    face = {"face_id": "face-001", "bbox": [1, 2, 20, 22], "detection_confidence": 0.9,
            "movements": {"status": "succeeded"},
            "expression": {"status": "succeeded", "decision": "inconclusive", "best_class": "Neutral",
                           "scores": [{"label": "Neutral", "score": 0.4}, {"label": "Happiness", "score": 0.35}],
                           "calibrated": False}}
    face.update(changes)
    return face


FACES_IMAGE = {
    "operation": "face_analysis", "analysis_status": "completed", "width": 32, "height": 24,
    "image_base64": "SECRET-PREVIEW", "coverage": {"task_families_total": 3, "task_families_completed": 3},
    "detection": {"status": "succeeded", "detected_count": 1, "selected_count": 1, "omitted_count": 0},
    "faces": [_face()], "models": [{"model_id": "blaze_face_short_range"}],
}


def test_faces_table_with_uncalibrated_scores_and_no_image():
    md = vm.render_result({"image": FACES_IMAGE, "metadata": {"title": "grupo.png"}, "markdown": "old"}, job_id="j")
    assert md.startswith("# Análise facial da imagem\n\n- Estado da análise: `completed`\n- Cobertura: 3 de 3")
    assert "não calibradas" in md and "SECRET-PREVIEW" not in md
    assert ("| `face-001` | 1 | 2 | 20 | 22 | 0.9000 | succeeded | inconclusiva (melhor classe: Neutral) |") in md
    assert "### Scores de expressão de `face-001` (não calibrados)" in md
    assert "| Neutral | 0.4000 |" in md and "- Arquivo: grupo.png" in md
    estimated = vm.faces_section({"detection": {"status": "succeeded"}, "faces": [
        _face(expression={"decision": "estimated", "label": "Happiness", "scores": []})]})
    assert "| Happiness |" in estimated and "Scores de expressão" not in estimated
    empty = vm.faces_section({"detection": {"status": "succeeded"}, "faces": []})
    assert empty.endswith("Nenhum rosto detectado.")


def test_full_report_sections():
    step = lambda task, i=0, **kw: {"step_id": task.strip("<>").lower() + f"-{i}", "task": task,
                                    "status": "succeeded", "text": "", "regions": [], "lines": [], **kw}
    image = {
        "operation": "full_analysis", "profile": "image-full-v2", "analysis_status": "partial",
        "reason_code": "deadline_exceeded", "width": 64, "height": 48, "model": MODEL_INFO,
        "image_base64": "SECRET-PREVIEW", "description": "A car on a street.",
        "coverage": {"task_families_total": 18, "task_families_completed": 16},
        "results": [
            step("<MORE_DETAILED_CAPTION>", text="A car on a street."),
            step("<OCR_WITH_REGION>", text="STOP\nAHEAD", lines=[{"text": "STOP"}, {"text": "AHEAD"}]),
            step("<OD>", text="car", regions=[{"label": "car", "bbox": [1, 2, 3, 4], "score": 0.5}]),
            {**step("<REGION_TO_OCR>"), "status": "failed", "reason_code": "inference_failed",
             "input": {"region": [0, 0, 1, 1]}},
            {"step_id": "face_detection", "task": "face_detection", "kind": "face", "status": "succeeded"},
        ],
        "faces": {"detection": {"status": "succeeded", "selected_count": 1}, "faces": [_face()]},
    }
    md = vm.render_result({"image": image, "metadata": {"title": "rua.png"}}, job_id="job-full")
    assert md.startswith("# Análise completa da imagem\n\n- Estado da análise: `partial` (`deadline_exceeded`)\n"
                         "- Perfil: `image-full-v2`\n- Cobertura: 16 de 18 famílias de tarefas\n\n"
                         "## Descrição\n\nA car on a street.\n\n## Texto (OCR)\n\nSTOP  \nAHEAD\n\n## Detecções\n\n")
    assert "| Detectar objetos | car | 1 | 2 | 3 | 4 | 0.5000 |" in md
    assert "## Rostos e expressões" in md and "| `face-001` |" in md
    assert "### Extrair texto de uma região · `region_to_ocr-0`\n\n- Estado: `failed` (`inference_failed`)" in md
    assert "`face_detection`" not in md.split("## Resultados por tarefa")[1]
    assert "SECRET-PREVIEW" not in md and md.endswith("- Job: `job-full`\n")
    empty = vm.render_full({"operation": "full_analysis", "analysis_status": "failed", "results": []})
    assert "## Texto (OCR)\n\nNenhum texto detectado." in empty


def test_stored_result_dispatch_and_fallback():
    stored = vision_result({**OCR_PAYLOAD}, operation="ocr", image_bytes=PNG_BYTES, mime="image/png",
                           filename="nf.png")
    md = vm.render_result(stored, job_id="job-ocr")
    assert md.startswith("# Texto da imagem\n\nINGESTIFY  \nnota fiscal") and "- Arquivo: nf.png" in md
    assert PNG_B64 not in md
    assert vm.render_result({"markdown": "legacy *text*"}, job_id="x").startswith(
        "# Resultado da imagem\n\nlegacy \\*text\\*")


# ---------------------------------------------------------------------------
# Synchronous routes
# ---------------------------------------------------------------------------

ROUTES = [
    ("describe", "/images/describe", DESCRIBE_PAYLOAD, {}, "# Descrição da imagem\n\nUm quadrado azul"),
    ("ocr", "/images/ocr", OCR_PAYLOAD, {}, "# Texto da imagem\n\nINGESTIFY  \nnota fiscal"),
    ("analyze", "/images/analyze", ANALYZE_PAYLOAD, {"task": "<OD>", "wait": True}, "# Detectar objetos\n\n## Regiões"),
]


def _call(app, path, payload, extra, user, multipart, output_format=None):
    if multipart:
        fields = {k: (str(v).lower() if isinstance(v, bool) else v) for k, v in extra.items()}
        if output_format is not None:
            fields["output_format"] = output_format
        return _post_multipart(app, path + "/upload", fields=fields, file_field=_png_upload("foto.png"), user=user)
    body = {"image_base64": PNG_B64, "filename": "foto.png", **extra}
    if output_format is not None:
        body["output_format"] = output_format
    return _post_json(app, path, body, user=user)


@pytest.mark.parametrize("multipart", [False, True], ids=["json", "multipart"])
@pytest.mark.parametrize("kind,path,payload,extra,start", ROUTES, ids=[r[0] for r in ROUTES])
def test_markdown_on_sync_success_and_stored_as_default(app, db, users, install_dispatch, kind, path, payload,
                                                        extra, start, multipart):
    install_dispatch(result=payload)
    response = _call(app, path, payload, extra, users, multipart, "markdown")
    assert response.status_code == 200, response.body
    assert response.headers["content-type"] == MARKDOWN
    text = response.body.decode()
    assert text.startswith(start) and "- Arquivo: foto.png" in text
    assert PNG_B64 not in text
    job = db.query(Job).one()
    assert f"- Job: `{job.id}`" in text
    assert job.configuration_row.options["output_format"] == "markdown"


@pytest.mark.parametrize("multipart", [False, True], ids=["json", "multipart"])
@pytest.mark.parametrize("kind,path,payload,extra,start", ROUTES, ids=[r[0] for r in ROUTES])
def test_default_and_explicit_json_are_byte_identical(app, db, users, install_dispatch, kind, path, payload,
                                                      extra, start, multipart):
    install_dispatch(result=payload)
    default = _call(app, path, payload, extra, users, multipart)
    explicit = _call(app, path, payload, extra, users, multipart, "json")
    assert default.status_code == explicit.status_code == 200
    assert default.headers["content-type"] == "application/json"
    first, second = default.json(), explicit.json()
    assert first.pop("job_id") != second.pop("job_id")
    # the project is created by the first request only
    assert first.pop("project")["created"] is True and second.pop("project")["created"] is False
    assert first == second and first["image_base64"] == PNG_B64
    model = {"describe": ImageDescribeResponse, "ocr": ImageOcrResponse, "analyze": ImageAnalyzeResponse}[kind]
    assert set(default.json()) == set(model.model_fields)
    # nothing new is written on the job by default (its configuration is unchanged)
    for job in db.query(Job).all():
        assert "output_format" not in job.configuration_row.options


@pytest.mark.parametrize("multipart", [False, True], ids=["json", "multipart"])
@pytest.mark.parametrize("kind,path,payload,extra,start", ROUTES, ids=[r[0] for r in ROUTES])
def test_invalid_output_format_is_422_and_creates_nothing(app, db, users, install_dispatch, kind, path, payload,
                                                          extra, start, multipart):
    fake = install_dispatch(result=payload)
    response = _call(app, path, payload, extra, users, multipart, "html")
    assert response.status_code == 422
    assert fake.calls == [] and db.query(Job).count() == 0


def test_queued_and_timeout_stay_json(app, db, users, install_dispatch, monkeypatch):
    import api.image_routes as image_routes
    install_dispatch(result=ANALYZE_PAYLOAD)
    queued = _post_json(app, "/images/analyze", {"image_base64": PNG_B64, "task": "<OD>",
                                                 "output_format": "markdown"}, user=users)
    assert queued.status_code == 202 and queued.headers["content-type"] == "application/json"
    assert db.get(Job, queued.json()["job_id"]).configuration_row.options["output_format"] == "markdown"
    install_dispatch(result=None, ready=False)
    monkeypatch.setattr(image_routes.settings, "vision_request_timeout_seconds", 0)
    timeout = _post_json(app, "/images/describe", {"image_base64": PNG_B64, "output_format": "markdown"}, user=users)
    assert timeout.status_code == 504 and timeout.detail["error_code"] == "VISION_TIMEOUT"
    install_dispatch(result={"ok": False, "error_code": "VISION_UNAVAILABLE", "http_status": 503, "detail": "x"})
    failed = _post_json(app, "/images/ocr", {"image_base64": PNG_B64, "output_format": "markdown"}, user=users)
    assert failed.status_code == 503 and failed.headers["content-type"] == "application/json"


# ---------------------------------------------------------------------------
# GET /jobs/{job_id}/result?format=
# ---------------------------------------------------------------------------

class NoElasticsearch:
    def get_job_result(self, job_id):
        return None


@pytest.fixture
def result_app(app, monkeypatch, no_redis):
    from api import routes
    monkeypatch.setattr(routes, "get_redis_client", lambda: no_redis)
    monkeypatch.setattr(routes, "get_es_client", lambda: NoElasticsearch())
    app.include_router(routes.router)
    return app


def _complete(no_redis, job_id, payload, operation):
    stored = vision_result({**payload, "job_id": job_id}, operation=operation, image_bytes=PNG_BYTES,
                           mime="image/png", filename="foto.png")
    no_redis.set_job_result(job_id, stored)
    no_redis.set_job_status(job_id=job_id, job_type="main", status="completed", progress=100,
                            completed_at=datetime(2026, 10, 8, 12, 0, 0))


def _get(app, path, user, query=""):
    """A GET through the app in-process (the shared helper carries no query string)."""
    import asyncio
    from shared.auth import get_current_active_user
    from tests.test_images_endpoints import Response

    app.dependency_overrides[get_current_active_user] = lambda: user
    scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.1"}, "http_version": "1.1",
             "method": "GET", "scheme": "http", "path": path, "raw_path": path.encode(),
             "query_string": query.encode(), "root_path": "", "headers": [(b"host", b"localhost:8000")],
             "client": ("127.0.0.1", 51234), "server": ("localhost", 8000)}
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    asyncio.run(app(scope, receive, send))
    start = next(m for m in messages if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    return Response(start["status"], start["headers"], body)


@pytest.mark.parametrize("kind,path,payload,extra,start", ROUTES, ids=[r[0] for r in ROUTES])
def test_result_format_query_and_stored_default(result_app, db, users, install_dispatch, no_redis, kind, path,
                                                payload, extra, start):
    install_dispatch(result=payload)
    as_json = _call(result_app, path, payload, extra, users, False)
    as_markdown = _call(result_app, path, payload, extra, users, False, "markdown")
    json_job = as_json.json()["job_id"]
    markdown_job = db.query(Job).filter(Job.id != json_job).one().id
    for job_id in (json_job, markdown_job):
        _complete(no_redis, job_id, payload, kind)

    default = _get(result_app, f"/jobs/{json_job}/result", users)
    assert default.status_code == 200 and default.headers["content-type"] == "application/json"
    assert default.json()["result"]["image"]["operation"] == kind
    explicit = _get(result_app, f"/jobs/{json_job}/result", users, "format=json")
    assert explicit.body == default.body
    rendered = _get(result_app, f"/jobs/{json_job}/result", users, "format=markdown")
    assert rendered.status_code == 200 and rendered.headers["content-type"] == MARKDOWN
    assert rendered.body.decode().startswith(start) and f"- Job: `{json_job}`" in rendered.body.decode()

    # created with output_format=markdown: that is the default; ?format=json still reads the JSON
    stored = _get(result_app, f"/jobs/{markdown_job}/result", users)
    assert stored.headers["content-type"] == MARKDOWN and stored.body.decode().startswith(start)
    back = _get(result_app, f"/jobs/{markdown_job}/result", users, "format=json")
    assert back.headers["content-type"] == "application/json"
    assert back.json()["result"]["image"]["operation"] == kind


def test_result_format_errors_per_job_kind(result_app, db, users, install_dispatch, no_redis):
    install_dispatch(result=OCR_PAYLOAD)
    job_id = _post_json(result_app, "/images/ocr", {"image_base64": PNG_B64}, user=users).json()["job_id"]
    _complete(no_redis, job_id, OCR_PAYLOAD, "ocr")
    for fmt in ("vtt", "srt", "txt"):
        response = _get(result_app, f"/jobs/{job_id}/result", users, f"format={fmt}")
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert detail["code"] == "IMAGE_RESULT_FORMAT_UNSUPPORTED"
        assert "OCR de imagem" in detail["message"] and fmt in detail["message"]
    bogus = _get(result_app, f"/jobs/{job_id}/result", users, "format=html")
    assert bogus.status_code == 422 and bogus.json()["detail"]["code"] == "RESULT_FORMAT_INVALID"
    assert "html" in bogus.json()["detail"]["message"]


def test_every_image_route_publishes_output_format_and_markdown():
    from api.main import app
    schema = app.openapi()
    components = schema["components"]["schemas"]
    assert schema["info"]["version"] == "1.4.0"
    for path in ("/images/describe/upload", "/images/ocr/upload", "/images/analyze/upload",
                 "/images/faces/upload", "/images/describe", "/images/ocr", "/images/analyze", "/images/faces"):
        operation = schema["paths"][path]["post"]
        content = operation["requestBody"]["content"]
        media = content.get("multipart/form-data") or content["application/json"]
        refs = [media["schema"]] if "$ref" in media["schema"] else media["schema"].get("anyOf") or media["schema"]["oneOf"]
        for ref in refs:
            field = components[ref["$ref"].rsplit("/", 1)[-1]]["properties"]["output_format"]
            assert field["enum"] == ["json", "markdown"] and field["default"] == "json", path
        assert "text/markdown" in operation["responses"]["200"]["content"], path
    result = schema["paths"]["/jobs/{job_id}/result"]["get"]
    assert "text/markdown" in result["responses"]["200"]["content"]
    assert "markdown" in next(p for p in result["parameters"] if p["name"] == "format")["description"]
