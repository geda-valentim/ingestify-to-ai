"""
Markdown rendering of image job results: `output_format=markdown` on the eight
`/images/*` routes and `GET /jobs/{job_id}/result?format=markdown` of an image job.

The JSON stays the contract; this is a second view of the same data, so the
renderer is pure (no I/O, no clock) and deterministic: the same result always
gives the same bytes.

Model text is untrusted (a caption or an OCR line can contain anything), so every
piece of it goes through `text()` / `cell()`: `figure_descriptions.clean_text`
first (control characters, Florence tokens, `<!--`), then the characters that
would open HTML or Markdown structure are escaped (`<`/`>` as entities, `*`, `_`,
`` ` ``, `[`, `]`, `|`, `\\` with a backslash, and a block marker at the start of a
line: `#`, `-`, `+`, `=`, `~`, `1.`). Identifiers (task, model, job id) go in code
spans with backticks removed.

Never embeds `image_base64` or previews: only text, boxes and scores.
Headings are in Portuguese (the API's documentation language); model output stays
as produced (Florence-2 captions are in English).
"""
import math
import re
from typing import Any, Dict, Iterable, List, Optional

from shared.figure_descriptions import clean_text
from shared.vision_capabilities import VISION_TASKS

MEDIA_TYPE = "text/markdown; charset=utf-8"
# What a starlette Response is given: it appends "; charset=utf-8" to text/* itself
RESPONSE_MEDIA_TYPE = "text/markdown"
OUTPUT_FORMATS = ("json", "markdown")
DEFAULT_OUTPUT_FORMAT = "json"

NO_TEXT = "Nenhum texto detectado."
NO_RESULT = "Nenhum resultado detectado."
FACES_NOTE = ("Estimativa de expressão visível; não determina o estado emocional. "
              "Os scores de expressão são probabilidades softmax não calibradas.")

# Tasks whose regions are detections (boxes with a label) in a full analysis
DETECTION_TASKS = ("<OD>", "<DENSE_REGION_CAPTION>", "<REGION_PROPOSAL>",
                   "<CAPTION_TO_PHRASE_GROUNDING>", "<OPEN_VOCABULARY_DETECTION>")
FACIAL_STEPS = ("face_detection", "face_movements", "face_expression_classification")

_INLINE = str.maketrans({
    "\\": "\\\\", "`": "\\`", "*": "\\*", "_": "\\_", "[": "\\[", "]": "\\]",
    "|": "\\|", "<": "&lt;", ">": "&gt;",
})
_BLOCK_START = re.compile(r"^[#+\-=~]")
_ORDERED_START = re.compile(r"^(\d+)([.)])")


# ---------------------------------------------------------------------------
# Escaping
# ---------------------------------------------------------------------------

def text(value: Any) -> str:
    """Untrusted text as Markdown text: line breaks kept, structure escaped."""
    cleaned = clean_text(value if isinstance(value, str) else ("" if value is None else str(value)), 0)
    lines = []
    for line in cleaned.split("\n"):
        line = line.translate(_INLINE)
        line = _BLOCK_START.sub(lambda m: "\\" + m.group(0), line)
        lines.append(_ORDERED_START.sub(lambda m: m.group(1) + "\\" + m.group(2), line))
    return "\n".join(lines)


def cell(value: Any) -> str:
    """Untrusted text inside a table cell: one line."""
    escaped = " ".join(part for part in text(value).split("\n") if part)
    return escaped or "—"


def code(value: Any) -> str:
    """An identifier in a code span (backticks and line breaks removed)."""
    raw = "" if value is None else str(value)
    raw = " ".join(raw.replace("`", "").split())
    return f"`{raw}`" if raw else "—"


def number(value: Any, digits: int = 2) -> str:
    """A coordinate or score: integers as integers, otherwise at most `digits` decimals."""
    try:
        result = float(value)
    except (TypeError, ValueError):
        return "—"
    if not math.isfinite(result):
        return "—"
    if result == int(result):
        return str(int(result))
    return f"{result:.{digits}f}".rstrip("0").rstrip(".")


def score(value: Any) -> str:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return "—"
    return f"{result:.4f}" if math.isfinite(result) else "—"


def _lines_block(lines: Iterable[Any]) -> str:
    """One output line per Markdown line (hard break: two trailing spaces)."""
    rendered = [line for line in (text(item) for item in lines) if line]
    flat = [part for line in rendered for part in line.split("\n") if part]
    return "  \n".join(flat)


def _table(header: List[str], rows: List[List[str]]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join(" --- " for _ in header) + "|"]
    out += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(out)


def _document(sections: List[str]) -> str:
    return "\n\n".join(section for section in sections if section) + "\n"


# ---------------------------------------------------------------------------
# Shared pieces
# ---------------------------------------------------------------------------

def task_label(task: Any) -> str:
    return VISION_TASKS[task][0] if task in VISION_TASKS else "Tarefa de visão"


def _model_line(model: Any) -> Optional[str]:
    if not isinstance(model, dict) or not model.get("model_id"):
        return None
    line = f"- Modelo: {code(model.get('model_id'))}"
    if model.get("revision"):
        line += f" (revisão {code(model.get('revision'))})"
    return line


def _metadata(image: Dict[str, Any], *, job_id=None, filename=None, task=None, extra=()) -> str:
    items = []
    if filename:
        items.append(f"- Arquivo: {cell(filename)}")
    if image.get("width") and image.get("height"):
        items.append(f"- Dimensões: {number(image['width'])} × {number(image['height'])} px")
    model_line = _model_line(image.get("model"))
    if model_line:
        items.append(model_line)
    if task:
        items.append(f"- Tarefa: {task_label(task)} ({code(task)})")
    items.extend(extra)
    if job_id:
        items.append(f"- Job: {code(job_id)}")
    return "## Metadados\n\n" + "\n".join(items) if items else ""


def _region_rows(regions: Iterable[Any], *, task_column: Optional[str] = None):
    """Rows of the regions that carry a bbox, and how many have only polygons."""
    rows, polygons_only, with_score = [], 0, False
    for region in regions or []:
        if not isinstance(region, dict):
            continue
        bbox = region.get("bbox")
        if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
            with_score = with_score or region.get("score") is not None
            rows.append((region, bbox))
        elif region.get("polygons"):
            polygons_only += 1
    return rows, polygons_only, with_score


def regions_table(regions: Iterable[Any], *, tasks: Optional[List[Any]] = None) -> str:
    """Label, x_min, y_min, x_max, y_max (as returned: pixels of the original image)."""
    rows, polygons_only, with_score = _region_rows(regions)
    parts = []
    if rows:
        header = (["Tarefa"] if tasks is not None else []) + ["Rótulo", "x_min", "y_min", "x_max", "y_max"]
        if with_score:
            header.append("Score")
        body = []
        for index, (region, bbox) in enumerate(rows):
            row = ([cell(task_label(tasks[index]))] if tasks is not None else [])
            row += [cell(region.get("label"))] + [number(value) for value in bbox]
            if with_score:
                row.append(score(region.get("score")) if region.get("score") is not None else "—")
            body.append(row)
        parts.append(_table(header, body))
    if polygons_only:
        parts.append(f"{polygons_only} região(ões) só com polígonos de segmentação; "
                     "as coordenadas estão no JSON (`format=json`).")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Per job kind
# ---------------------------------------------------------------------------

def render_describe(image: Dict[str, Any], *, job_id=None, filename=None) -> str:
    description = text(image.get("description"))
    return _document([
        "# Descrição da imagem",
        description or NO_RESULT,
        _metadata(image, job_id=job_id, filename=filename, task=image.get("task") or "<MORE_DETAILED_CAPTION>"),
    ])


def _ocr_lines(image: Dict[str, Any]) -> List[Any]:
    lines = image.get("lines") or []
    if lines:
        return [line.get("text") if isinstance(line, dict) else line for line in lines]
    return (image.get("text") or "").split("\n")


def render_ocr(image: Dict[str, Any], *, job_id=None, filename=None) -> str:
    body = _lines_block(_ocr_lines(image))
    return _document([
        "# Texto da imagem",
        body or NO_TEXT,
        _metadata(image, job_id=job_id, filename=filename, task=image.get("task") or "<OCR_WITH_REGION>"),
    ])


def _analysis_text(task: Any, raw_text: Any, regions: Iterable[Any]) -> str:
    """The text of a single task, unless it only repeats the region labels."""
    labels = [r.get("label") or "" for r in regions or [] if isinstance(r, dict)]
    if labels and (raw_text or "") == "\n".join(label for label in labels if label):
        return ""
    return _lines_block((raw_text or "").split("\n"))


def render_analyze(image: Dict[str, Any], *, job_id=None, filename=None) -> str:
    task = image.get("task")
    regions = image.get("regions") or []
    body = _analysis_text(task, image.get("text"), regions)
    table = regions_table(regions)
    request = image.get("request") if isinstance(image.get("request"), dict) else {}
    extra = []
    if request.get("text_input"):
        extra.append(f"- Entrada de texto: {cell(request['text_input'])}")
    if request.get("region"):
        extra.append("- Região pedida (normalizada): " + ", ".join(number(v, 4) for v in request["region"]))
    return _document([
        f"# {task_label(task)}",
        body if body or table else NO_RESULT,
        f"## Regiões\n\n{table}" if table else "",
        _metadata(image, job_id=job_id, filename=filename, task=task, extra=extra),
    ])


def _status_line(image: Dict[str, Any]) -> str:
    line = f"- Estado da análise: {code(image.get('analysis_status'))}"
    if image.get("reason_code"):
        line += f" ({code(image.get('reason_code'))})"
    return line


def _coverage_line(image: Dict[str, Any]) -> Optional[str]:
    coverage = image.get("coverage")
    if not isinstance(coverage, dict) or "task_families_total" not in coverage:
        return None
    return (f"- Cobertura: {number(coverage.get('task_families_completed', 0))} de "
            f"{number(coverage.get('task_families_total'))} famílias de tarefas")


def faces_section(block: Dict[str, Any], *, level: int = 2) -> str:
    """Faces table (box in pixels, detection confidence, expression) and the uncalibrated scores."""
    heading = "#" * level
    detection = block.get("detection") or {}
    parts = [f"{heading} Rostos e expressões", FACES_NOTE,
             f"- Detecção: {code(detection.get('status'))}"
             + (f" ({code(detection.get('reason_code'))})" if detection.get("reason_code") else "")
             + f"; detectados: {number(detection.get('detected_count', 0))}"
             f"; selecionados: {number(detection.get('selected_count', 0))}"
             f"; omitidos: {number(detection.get('omitted_count', 0))}"]
    faces = [face for face in block.get("faces") or [] if isinstance(face, dict)]
    if not faces:
        parts.append("Nenhum rosto detectado.")
        return "\n\n".join(parts)
    rows = []
    for face in faces:
        bbox = face.get("bbox") or [None] * 4
        movements = face.get("movements") or {}
        rows.append([code(face.get("face_id")), *[number(value) for value in bbox[:4]],
                     score(face.get("detection_confidence")),
                     cell(movements.get("status")), _expression_cell(face.get("expression") or {})])
    parts.append(_table(["Rosto", "x_min", "y_min", "x_max", "y_max", "Confiança da detecção",
                         "Movimentos", "Expressão"], rows))
    for face in faces:
        scores = (face.get("expression") or {}).get("scores") or []
        if scores:
            parts.append(f"{heading}# Scores de expressão de {code(face.get('face_id'))} (não calibrados)\n\n"
                         + _table(["Expressão", "Score"],
                                  [[cell(item.get("label")), score(item.get("score"))]
                                   for item in scores if isinstance(item, dict)]))
    return "\n\n".join(parts)


def _expression_cell(expression: Dict[str, Any]) -> str:
    decision = expression.get("decision")
    if decision == "estimated" and expression.get("label"):
        return cell(expression["label"])
    if decision == "inconclusive":
        best = expression.get("best_class")
        return "inconclusiva" + (f" (melhor classe: {cell(best)})" if best else "")
    status = expression.get("status")
    reason = expression.get("reason_code")
    return cell(status) + (f" ({cell(reason)})" if reason else "") if status else "—"


def _step_section(step: Dict[str, Any]) -> str:
    task = step.get("task")
    lines = [f"### {task_label(task)} · {code(step.get('step_id'))}"]
    status = f"- Estado: {code(step.get('status'))}"
    if step.get("reason_code"):
        status += f" ({code(step.get('reason_code'))})"
    details = [status]
    given = step.get("input") or {}
    if given.get("text_input"):
        details.append(f"- Entrada de texto: {cell(given['text_input'])}")
    if given.get("region"):
        details.append("- Região (normalizada): " + ", ".join(number(v, 4) for v in given["region"]))
    lines.append("\n".join(details))
    if step.get("status") == "succeeded":
        regions = step.get("regions") or []
        body = (_lines_block(line.get("text") for line in step.get("lines") or [] if isinstance(line, dict))
                if step.get("lines") else _analysis_text(task, step.get("text"), regions))
        if body:
            lines.append(body)
        elif regions and task in DETECTION_TASKS:
            lines.append(f"{len(regions)} região(ões); ver Detecções.")
        elif regions:
            lines.append(regions_table(regions))
        else:
            lines.append(NO_RESULT)
    return "\n\n".join(lines)


def render_full(image: Dict[str, Any], *, job_id=None, filename=None) -> str:
    steps = [step for step in image.get("results") or []
             if isinstance(step, dict) and step.get("task") not in FACIAL_STEPS]
    succeeded = {}
    for step in steps:
        if step.get("status") == "succeeded":
            succeeded.setdefault(step.get("task"), step)

    ocr = succeeded.get("<OCR_WITH_REGION>")
    ocr_body = _lines_block(line.get("text") for line in (ocr or {}).get("lines") or [] if isinstance(line, dict))
    if not ocr_body and ocr:
        ocr_body = _lines_block((ocr.get("text") or "").split("\n"))
    if not ocr_body and succeeded.get("<OCR>"):
        ocr_body = _lines_block((succeeded["<OCR>"].get("text") or "").split("\n"))

    detections, tasks = [], []
    for step in steps:
        if step.get("status") == "succeeded" and step.get("task") in DETECTION_TASKS:
            for region in step.get("regions") or []:
                detections.append(region)
                tasks.append(step.get("task"))
    table = regions_table(detections, tasks=tasks)

    summary = [_status_line(image), f"- Perfil: {code(image.get('profile') or 'image-full-v1')}"]
    if _coverage_line(image):
        summary.append(_coverage_line(image))
    faces = image.get("faces") if isinstance(image.get("faces"), dict) else None
    return _document([
        "# Análise completa da imagem",
        "\n".join(summary),
        "## Descrição\n\n" + (text(image.get("description")) or NO_RESULT),
        "## Texto (OCR)\n\n" + (ocr_body or NO_TEXT),
        "## Detecções\n\n" + (table or NO_RESULT),
        faces_section(faces) if faces else "",
        "## Resultados por tarefa\n\n" + ("\n\n".join(_step_section(step) for step in steps) or NO_RESULT),
        _metadata(image, job_id=job_id, filename=filename),
    ])


def render_faces(image: Dict[str, Any], *, job_id=None, filename=None) -> str:
    summary = [_status_line(image)]
    if _coverage_line(image):
        summary.append(_coverage_line(image))
    models = [model.get("model_id") for model in image.get("models") or []
              if isinstance(model, dict) and model.get("model_id")]
    extra = [f"- Modelos: {', '.join(code(model) for model in models)}"] if models else []
    return _document([
        "# Análise facial da imagem",
        "\n".join(summary),
        faces_section(image),
        _metadata(image, job_id=job_id, filename=filename, extra=extra),
    ])


RENDERERS = {
    "describe": render_describe,
    "ocr": render_ocr,
    "analyze": render_analyze,
    "full_analysis": render_full,
    "face_analysis": render_faces,
}


def render_image(image: Dict[str, Any], *, operation: Optional[str] = None, job_id=None, filename=None) -> str:
    """Render one image record (the `image` of a stored result, or a sync response)."""
    operation = operation or image.get("operation")
    renderer = RENDERERS.get(operation)
    if renderer is None:
        return _document(["# Resultado da imagem", text(image.get("text") or image.get("description")) or NO_RESULT,
                          _metadata(image, job_id=job_id, filename=filename)])
    return renderer(image, job_id=job_id, filename=filename)


def render_result(result: Dict[str, Any], *, job_id=None) -> str:
    """Render a stored image job result (`{markdown, image, metadata}`)."""
    result = result if isinstance(result, dict) else {}
    image = result.get("image") if isinstance(result.get("image"), dict) else None
    filename = (result.get("metadata") or {}).get("title")
    if image is None:
        return _document(["# Resultado da imagem", text(result.get("markdown")) or NO_RESULT,
                          _metadata({}, job_id=job_id, filename=filename)])
    return render_image(image, job_id=job_id, filename=filename)
