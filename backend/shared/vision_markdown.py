"""
Markdown rendering of image job results: `output_format=markdown` on the eight
`/images/*` routes and `GET /jobs/{job_id}/result?format=markdown` of an image job.

The JSON stays the contract; this is a second view of the same data, so the
renderer is pure (no I/O, no clock) and deterministic: the same result always
gives the same bytes. It never raises on a malformed result: a field of the wrong
type renders as `—` (or is skipped), never as a 500.

Model text is untrusted (a caption or an OCR line can contain anything), so every
piece of it goes through `text()` / `cell()`: `&` becomes `&amp;` (so `&lt;b&gt;`
shows literally), `figure_descriptions.clean_text` runs (control characters,
Florence tokens, `<!--`), then the characters that would open HTML or Markdown
structure are escaped (`<`/`>` as entities, `*`, `_`, `` ` ``, `[`, `]`, `|`, `\\`
with a backslash, and a block marker at the start of a line: `#`, `-`, `+`, `=`,
`~`, `1.`), and bare URLs / e-mails are kept from autolinking (`://` → `:&#47;&#47;`,
`www.` → `www&#46;`, `@` → `&#64;`; they still read the same). Identifiers (task,
model, job id) go in code spans with backticks removed.

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
_WWW = re.compile(r"(?i)\b(www)\.")


# ---------------------------------------------------------------------------
# Type guards: a malformed result renders, it never raises
# ---------------------------------------------------------------------------

def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _l(value: Any) -> List[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _s(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None or isinstance(value, (dict, list, tuple)):
        return ""
    return str(value)


def _four(value: Any) -> List[Any]:
    """A box as exactly 4 entries (missing ones render as `—`)."""
    box = _l(value)[:4]
    return box + [None] * (4 - len(box))


# ---------------------------------------------------------------------------
# Escaping
# ---------------------------------------------------------------------------

def text(value: Any) -> str:
    """Untrusted text as Markdown text: line breaks kept, structure escaped."""
    cleaned = clean_text(_s(value).replace("&", "&amp;"), 0)
    lines = []
    for line in cleaned.split("\n"):
        line = line.translate(_INLINE)
        line = line.replace("://", ":&#47;&#47;").replace("@", "&#64;")
        line = _WWW.sub(lambda m: m.group(1) + "&#46;", line)
        line = _BLOCK_START.sub(lambda m: "\\" + m.group(0), line)
        lines.append(_ORDERED_START.sub(lambda m: m.group(1) + "\\" + m.group(2), line))
    return "\n".join(lines)


def cell(value: Any) -> str:
    """Untrusted text inside a table cell: one line."""
    escaped = " ".join(part for part in text(value).split("\n") if part)
    return escaped or "—"


def code(value: Any) -> str:
    """An identifier in a code span (backticks and line breaks removed)."""
    raw = " ".join(_s(value).replace("`", "").split())
    return f"`{raw}`" if raw else "—"


def _finite(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def number(value: Any, digits: int = 2) -> str:
    """A coordinate or score: integers as integers, otherwise at most `digits` decimals."""
    result = _finite(value)
    if result is None:
        return "—"
    if result == int(result):
        return str(int(result))
    return f"{result:.{digits}f}".rstrip("0").rstrip(".")


def score(value: Any) -> str:
    result = _finite(value)
    return "—" if result is None else f"{result:.4f}"


def _lines_block(lines: Iterable[Any]) -> str:
    """One output line per Markdown line (hard break: two trailing spaces)."""
    flat = [part for item in lines for part in text(item).split("\n") if part]
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
    return VISION_TASKS[task][0] if isinstance(task, str) and task in VISION_TASKS else "Tarefa de visão"


def _model_line(model: Any) -> Optional[str]:
    model = _d(model)
    if not _s(model.get("model_id")):
        return None
    line = f"- Modelo: {code(model.get('model_id'))}"
    if _s(model.get("revision")):
        line += f" (revisão {code(model.get('revision'))})"
    return line


def _metadata(image: Dict[str, Any], *, job_id=None, filename=None, task=None, extra=()) -> str:
    items = []
    if _s(filename):
        items.append(f"- Arquivo: {cell(filename)}")
    if _finite(image.get("width")) and _finite(image.get("height")):
        items.append(f"- Dimensões: {number(image['width'])} × {number(image['height'])} px")
    model_line = _model_line(image.get("model"))
    if model_line:
        items.append(model_line)
    if _s(task):
        items.append(f"- Tarefa: {task_label(task)} ({code(task)})")
    items.extend(extra)
    if _s(job_id):
        items.append(f"- Job: {code(job_id)}")
    return "## Metadados\n\n" + "\n".join(items) if items else ""


def _region(value: Any) -> Optional[Dict[str, Any]]:
    """A region with a box (padded to 4 values), or None when it has none."""
    region = _d(value)
    box = _l(region.get("bbox"))
    return {**region, "bbox": _four(box)} if box else None


def regions_table(regions: Iterable[Any], *, tasks: Optional[List[Any]] = None) -> str:
    """Label, x_min, y_min, x_max, y_max (as returned: pixels of the original image)."""
    rows, polygons_only = [], 0
    for index, raw in enumerate(_l(regions)):
        region = _region(raw)
        if region is not None:
            rows.append((index, region))
        elif _l(_d(raw).get("polygons")):
            polygons_only += 1
    with_score = any(region.get("score") is not None for _, region in rows)
    parts = []
    if rows:
        header = (["Tarefa"] if tasks is not None else []) + ["Rótulo", "x_min", "y_min", "x_max", "y_max"]
        if with_score:
            header.append("Score")
        body = []
        for index, region in rows:
            row = [cell(task_label(tasks[index]))] if tasks is not None and index < len(tasks) else (
                ["—"] if tasks is not None else [])
            row += [cell(region.get("label"))] + [number(value) for value in region["bbox"]]
            if with_score:
                row.append(score(region.get("score")))
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
    image = _d(image)
    return _document([
        "# Descrição da imagem",
        text(image.get("description")) or NO_RESULT,
        _metadata(image, job_id=job_id, filename=filename, task=image.get("task") or "<MORE_DETAILED_CAPTION>"),
    ])


def _ocr_lines(image: Dict[str, Any]) -> List[Any]:
    lines = _l(image.get("lines"))
    if lines:
        return [_d(line).get("text") if isinstance(line, dict) else line for line in lines]
    return _s(image.get("text")).split("\n")


def render_ocr(image: Dict[str, Any], *, job_id=None, filename=None) -> str:
    image = _d(image)
    return _document([
        "# Texto da imagem",
        _lines_block(_ocr_lines(image)) or NO_TEXT,
        _metadata(image, job_id=job_id, filename=filename, task=image.get("task") or "<OCR_WITH_REGION>"),
    ])


def _analysis_text(raw_text: Any, regions: Any) -> str:
    """The text of a single task, unless it only repeats the region labels."""
    labels = [_s(_d(r).get("label")) for r in _l(regions)]
    raw = _s(raw_text)
    if labels and raw == "\n".join(label for label in labels if label):
        return ""
    return _lines_block(raw.split("\n"))


def render_analyze(image: Dict[str, Any], *, job_id=None, filename=None) -> str:
    image = _d(image)
    task = image.get("task")
    regions = _l(image.get("regions"))
    body = _analysis_text(image.get("text"), regions)
    table = regions_table(regions)
    request = _d(image.get("request"))
    extra = []
    if _s(request.get("text_input")):
        extra.append(f"- Entrada de texto: {cell(request['text_input'])}")
    if _l(request.get("region")):
        extra.append("- Região pedida (normalizada): " + ", ".join(number(v, 4) for v in _l(request["region"])))
    return _document([
        f"# {task_label(task)}",
        body if body or table else NO_RESULT,
        f"## Regiões\n\n{table}" if table else "",
        _metadata(image, job_id=job_id, filename=filename, task=task, extra=extra),
    ])


def _status_line(image: Dict[str, Any]) -> str:
    line = f"- Estado da análise: {code(image.get('analysis_status'))}"
    if _s(image.get("reason_code")):
        line += f" ({code(image.get('reason_code'))})"
    return line


def _coverage_line(image: Dict[str, Any]) -> Optional[str]:
    coverage = _d(image.get("coverage"))
    if "task_families_total" not in coverage:
        return None
    return (f"- Cobertura: {number(coverage.get('task_families_completed', 0))} de "
            f"{number(coverage.get('task_families_total'))} famílias de tarefas")


def faces_section(block: Any, *, level: int = 2) -> str:
    """Faces table (box in pixels, detection confidence, expression) and the uncalibrated scores."""
    block = _d(block)
    heading = "#" * level
    detection = _d(block.get("detection"))
    parts = [f"{heading} Rostos e expressões", FACES_NOTE,
             f"- Detecção: {code(detection.get('status'))}"
             + (f" ({code(detection.get('reason_code'))})" if _s(detection.get("reason_code")) else "")
             + f"; detectados: {number(detection.get('detected_count', 0))}"
             f"; selecionados: {number(detection.get('selected_count', 0))}"
             f"; omitidos: {number(detection.get('omitted_count', 0))}"]
    faces = [face for face in _l(block.get("faces")) if isinstance(face, dict)]
    if not faces:
        parts.append("Nenhum rosto detectado.")
        return "\n\n".join(parts)
    rows = []
    for face in faces:
        rows.append([code(face.get("face_id")), *[number(value) for value in _four(face.get("bbox"))],
                     score(face.get("detection_confidence")),
                     cell(_d(face.get("movements")).get("status")), _expression_cell(_d(face.get("expression")))])
    parts.append(_table(["Rosto", "x_min", "y_min", "x_max", "y_max", "Confiança da detecção",
                         "Movimentos", "Expressão"], rows))
    for face in faces:
        scores = [item for item in _l(_d(face.get("expression")).get("scores")) if isinstance(item, dict)]
        if scores:
            parts.append(f"{heading}# Scores de expressão de {code(face.get('face_id'))} (não calibrados)\n\n"
                         + _table(["Expressão", "Score"],
                                  [[cell(item.get("label")), score(item.get("score"))] for item in scores]))
    return "\n\n".join(parts)


def _expression_cell(expression: Dict[str, Any]) -> str:
    decision = expression.get("decision")
    if decision == "estimated" and _s(expression.get("label")):
        return cell(expression["label"])
    if decision == "inconclusive":
        best = _s(expression.get("best_class"))
        return "inconclusiva" + (f" (melhor classe: {cell(best)})" if best else "")
    status = _s(expression.get("status"))
    reason = _s(expression.get("reason_code"))
    return cell(status) + (f" ({cell(reason)})" if reason else "") if status else "—"


def _step_section(step: Dict[str, Any]) -> str:
    task = step.get("task")
    lines = [f"### {task_label(task)} · {code(step.get('step_id'))}"]
    status = f"- Estado: {code(step.get('status'))}"
    if _s(step.get("reason_code")):
        status += f" ({code(step.get('reason_code'))})"
    details = [status]
    given = _d(step.get("input"))
    if _s(given.get("text_input")):
        details.append(f"- Entrada de texto: {cell(given['text_input'])}")
    if _l(given.get("region")):
        details.append("- Região (normalizada): " + ", ".join(number(v, 4) for v in _l(given["region"])))
    lines.append("\n".join(details))
    if step.get("status") == "succeeded":
        regions = _l(step.get("regions"))
        step_lines = _l(step.get("lines"))
        body = (_lines_block(_d(line).get("text") for line in step_lines)
                if step_lines else _analysis_text(step.get("text"), regions))
        if body:
            lines.append(body)
        elif regions and task in DETECTION_TASKS:
            lines.append(f"{len(regions)} região(ões); ver Detecções.")
        elif regions:
            lines.append(regions_table(regions) or NO_RESULT)
        else:
            lines.append(NO_RESULT)
    return "\n\n".join(lines)


def render_full(image: Dict[str, Any], *, job_id=None, filename=None) -> str:
    image = _d(image)
    steps = [step for step in _l(image.get("results"))
             if isinstance(step, dict) and step.get("task") not in FACIAL_STEPS]
    succeeded = {}
    for step in steps:
        if step.get("status") == "succeeded" and isinstance(step.get("task"), str):
            succeeded.setdefault(step["task"], step)

    ocr = succeeded.get("<OCR_WITH_REGION>") or {}
    ocr_body = _lines_block(_d(line).get("text") for line in _l(ocr.get("lines")))
    if not ocr_body and ocr:
        ocr_body = _lines_block(_s(ocr.get("text")).split("\n"))
    if not ocr_body and succeeded.get("<OCR>"):
        ocr_body = _lines_block(_s(succeeded["<OCR>"].get("text")).split("\n"))

    detections, tasks = [], []
    for step in steps:
        if step.get("status") == "succeeded" and step.get("task") in DETECTION_TASKS:
            for region in _l(step.get("regions")):
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
    image = _d(image)
    summary = [_status_line(image)]
    if _coverage_line(image):
        summary.append(_coverage_line(image))
    models = [_d(model).get("model_id") for model in _l(image.get("models")) if _s(_d(model).get("model_id"))]
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
    image = _d(image)
    operation = operation or image.get("operation")
    renderer = RENDERERS.get(operation) if isinstance(operation, str) else None
    if renderer is None:
        return _document(["# Resultado da imagem", text(image.get("text") or image.get("description")) or NO_RESULT,
                          _metadata(image, job_id=job_id, filename=filename)])
    return renderer(image, job_id=job_id, filename=filename)


def render_result(result: Dict[str, Any], *, job_id=None) -> str:
    """Render a stored image job result (`{markdown, image, metadata}`)."""
    result = _d(result)
    image = result.get("image") if isinstance(result.get("image"), dict) else None
    filename = _d(result.get("metadata")).get("title")
    if image is None:
        return _document(["# Resultado da imagem", text(result.get("markdown")) or NO_RESULT,
                          _metadata({}, job_id=job_id, filename=filename)])
    return render_image(image, job_id=job_id, filename=filename)
