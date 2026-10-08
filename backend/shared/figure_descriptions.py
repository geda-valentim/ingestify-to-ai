"""
Figure descriptions / OCR of a document conversion (`describe_images`,
`ocr_images` on /upload and /convert).

Only *figures* (docling PictureItems) are described, never page renders. The
captions come from Florence-2 on the vision worker and are in English.

Pipeline (workers/figure_tasks.py runs it, this module holds the pure parts):

1. extraction (workers/image_assets.extract_pictures): every figure of the
   document gets an *entry* (`name`, `page`, `sha256`, `object`, `anchor`,
   `skip`) in document order. With `image_mode=referenced` the figure is the
   stored asset and its anchor is the asset URL; with `image_mode=none` the PNG
   goes to a temporary area (`figures/{job_id}/` in the results bucket) and the
   markdown carries a marker `<!-- figure:{name} -->` where docling writes
   `<!-- image -->`. Figures below CONVERSION_ASSET_MIN_PX, unreadable ones and
   (none mode) those past CONVERSION_FIGURE_MAX_COUNT per page job are entries
   with `skip` set and keep the placeholder;
2. the describe stage starts once the whole markdown exists (after the single
   conversion, or after the merge of a split PDF): `plan` picks the unique images
   (sha256) in document order, at most CONVERSION_FIGURE_MAX_COUNT, and one
   vision task per unique image runs on the vision worker (caption and/or OCR);
3. the last vision task (or the stall watchdog) runs the finalize task, which
   `rewrite`s the markdown, completes the job and only then lets purge_source run.

Durable state: `figures/{job_id}/pending.json` (the converted result, the entries,
the work list) and `Job.figures_stage` / `figures_stage_at` (marker + heartbeat).
Redis keys (TTL cache, rebuilt from pending.json when lost): `job:{id}:figures:results`
(HASH sha256 -> JSON outcome), `:total`, `:stage` (work list + options), `:sent`
(HASH sha256 -> dispatch time: the in-flight window), `:backoff` / `:tick` (dispatch
retries), `:finalizing` (one finalize at a time); `job:{id}:figures:slots` /
`:bytes` (document-wide cap on the temporary PNGs of a split PDF).
"""
import json
import re
import unicodedata
from typing import Dict, Iterable, List, Optional, Tuple

FIGURE_AREA = "figures"
PENDING_NAME = "pending.json"
# Marker of a figure to describe in the markdown of an image_mode=none conversion,
# until the describe stage replaces it (with the description, or docling's placeholder)
MARKER = "<!-- figure:{name} -->"
_MARKER_RE = re.compile(r"<!-- figure:(p\d{4}-img\d{2,}-[0-9a-f]{12}\.png) -->")
PLACEHOLDER = "<!-- image -->"
# URI given to docling for a marked figure; replaced by the marker right after the export
MARKER_URI_PREFIX = "/ingestify-figure/"

OCR_TASK = "<OCR>"
CAPTION_TASKS = ("<CAPTION>", "<DETAILED_CAPTION>", "<MORE_DETAILED_CAPTION>")

DESCRIPTION_LABEL = "**Figure (description, English):**"
OCR_LABEL = "**Text in figure (OCR):**"

RESULTS_TTL_SECONDS = 24 * 3600


def figure_prefix(job_id: str) -> str:
    return f"{FIGURE_AREA}/{job_id}/"


def figure_object(job_id: str, name: str) -> str:
    return f"{figure_prefix(job_id)}{name}"


def pending_object(job_id: str) -> str:
    return f"{figure_prefix(job_id)}{PENDING_NAME}"


def marker(name: str) -> str:
    return MARKER.format(name=name)


def results_key(job_id: str) -> str:
    return f"job:{job_id}:figures:results"


def total_key(job_id: str) -> str:
    return f"job:{job_id}:figures:total"


def finalizing_key(job_id: str) -> str:
    return f"job:{job_id}:figures:finalizing"


def stage_key(job_id: str) -> str:
    return f"job:{job_id}:figures:stage"


def sent_key(job_id: str) -> str:
    return f"job:{job_id}:figures:sent"


def backoff_key(job_id: str) -> str:
    return f"job:{job_id}:figures:backoff"


def tick_key(job_id: str) -> str:
    return f"job:{job_id}:figures:tick"


def stage_keys(job_id: str) -> tuple:
    """Every Redis key of a describe stage (the finalize lock expires on its own)."""
    return (results_key(job_id), total_key(job_id), stage_key(job_id), sent_key(job_id), backoff_key(job_id),
            tick_key(job_id))


def caption_task(value: Optional[str]) -> str:
    """The configured caption task, or <MORE_DETAILED_CAPTION> when it is not a caption task."""
    return value if value in CAPTION_TASKS else "<MORE_DETAILED_CAPTION>"


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------

def plan(entries: Iterable[dict], max_count: int) -> List[dict]:
    """
    The vision work of a document: one item per unique image (sha256), in document
    order, at most `max_count`. Each item: {"sha256", "object"} (the first stored
    copy of those bytes). Entries with `skip` set are never sent.
    """
    work, seen = [], set()
    for entry in entries or []:
        sha = entry.get("sha256")
        if entry.get("skip") or not sha or not entry.get("object") or sha in seen:
            continue
        if len(work) >= max(0, int(max_count)):
            break
        seen.add(sha)
        work.append({"sha256": sha, "object": entry["object"]})
    return work


# ---------------------------------------------------------------------------
# Text
# ---------------------------------------------------------------------------

_SPACES = re.compile(r"[ \t ]+")
_BLANKS = re.compile(r"\n{2,}")


def clean_text(text, max_chars: int = 4000) -> str:
    """
    Model text made safe to inline in markdown: control characters stripped
    (newlines kept), whitespace collapsed, Florence's `</s>` / `<pad>` tokens
    dropped, `<!--` neutralised (it would hide what follows), cut at `max_chars`.
    """
    if not isinstance(text, str):
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("</s>", " ").replace("<s>", " ").replace("<pad>", " ")
    text = "".join(ch if ch == "\n" or (unicodedata.category(ch)[0] != "C") else " " for ch in text)
    text = text.replace("<!--", "&lt;!--").replace("-->", "--&gt;")
    lines = [_SPACES.sub(" ", line).strip() for line in text.split("\n")]
    text = _BLANKS.sub("\n\n", "\n".join(lines)).strip()
    if max_chars and len(text) > max_chars:
        text = text[:max_chars].rstrip() + "…"
    return text


def _quoted(label: str, text: str) -> str:
    lines = text.split("\n")
    out = [f"> {label} {lines[0]}"]
    out.extend(f"> {line}" if line else ">" for line in lines[1:])
    return "\n".join(out)


def blockquote(description: Optional[str], ocr_text: Optional[str]) -> str:
    """The quote inlined at a figure; "" when both texts are empty (the line is omitted)."""
    parts = []
    if description:
        parts.append(_quoted(DESCRIPTION_LABEL, description))
    if ocr_text:
        parts.append(_quoted(OCR_LABEL, ocr_text))
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Rewriting the markdown
# ---------------------------------------------------------------------------

def outcome_of(results: Dict[str, dict], sha: Optional[str]) -> dict:
    found = results.get(sha) if sha else None
    return found if isinstance(found, dict) else {}


def rewrite(markdown: str, entries: List[dict], results: Dict[str, dict], *, describe: bool, ocr: bool,
            max_chars: int = 4000) -> Tuple[str, dict, Dict[str, dict]]:
    """
    Inline the descriptions / OCR text at each figure, in document order.

    `results`: sha256 -> {"description": str | None, "ocr_text": str | None, ...}
    as the vision tasks recorded them (a key missing, or a None text, means that
    operation failed or never ran for the image).

    - anchor `<!-- figure:{name} -->` (image_mode=none): replaced by the quote, or by
      docling's `<!-- image -->` when there is nothing to say;
    - anchor = an asset URL (image_mode=referenced): the image reference is kept and
      the quote goes right after it.

    Returns (markdown, counts, texts): counts = {"figures_described",
    "figures_ocr", "figures_skipped"} per figure *position* (an image repeated
    twice counts twice); texts = name -> {"description", "ocr_text"} (cleaned).
    """
    counts = {"figures_described": 0, "figures_ocr": 0, "figures_skipped": 0}
    texts: Dict[str, dict] = {}
    markdown = markdown or ""
    for entry in entries or []:
        name = entry.get("name")
        outcome = {} if entry.get("skip") else outcome_of(results, entry.get("sha256"))
        description = outcome.get("description") if describe else None
        ocr_text = outcome.get("ocr_text") if ocr else None
        described = isinstance(description, str)
        read = isinstance(ocr_text, str)
        description = clean_text(description, max_chars) if described else None
        ocr_text = clean_text(ocr_text, max_chars) if read else None
        quote = blockquote(description, ocr_text)
        anchor = entry.get("anchor") or ""
        placed = False
        if anchor.startswith("<!--"):
            if anchor in markdown:
                markdown = markdown.replace(anchor, quote or PLACEHOLDER, 1)
                placed = True
        elif anchor:
            match = re.search(r"!\[[^\]]*\]\(" + re.escape(anchor) + r"\)", markdown)
            if match is not None:
                placed = True
                if quote:
                    end = match.end()
                    tail = markdown[end:]
                    after = "" if tail.startswith("\n\n") or not tail else ("\n" if tail.startswith("\n") else "\n\n")
                    markdown = markdown[:end] + "\n\n" + quote + after + tail
        if not placed:
            described = read = False
            description = ocr_text = None
        if name:
            texts[name] = {"description": description if described else None,
                           "ocr_text": ocr_text if read else None}
        counts["figures_described"] += int(described)
        counts["figures_ocr"] += int(read)
        counts["figures_skipped"] += int(not (described or read))
    # A marker nothing accounted for (never left in a published markdown)
    markdown = _MARKER_RE.sub(PLACEHOLDER, markdown)
    return markdown, counts, texts


def strip_markers(markdown: str) -> str:
    """Every figure marker back to docling's placeholder (a stage that cannot finish)."""
    return _MARKER_RE.sub(PLACEHOLDER, markdown or "")


def public_result(result):
    """A stored result without the private fields the merge reads (`_figures`, `_figure_markdown`)."""
    if not isinstance(result, dict):
        return result
    return {key: value for key, value in result.items() if not str(key).startswith("_")}


def page_outputs(result: dict) -> dict:
    """
    A page job's result with figure entries (describe_images / ocr_images): every
    public output (markdown, Elasticsearch, MySQL, MinIO) gets the markdown with the
    markers turned back into placeholders; the marked markdown and the entries stay in
    private fields only the merge reads.
    """
    entries = result.pop("figures", None)
    if entries is None:
        return result
    marked = result.get("markdown") or ""
    result["markdown"] = strip_markers(marked)
    result["_figure_markdown"] = marked
    result["_figures"] = entries
    return result


def annotate_assets(assets: Optional[list], texts: Dict[str, dict]) -> Optional[list]:
    """`description` / `ocr_text` on every asset (null for page renders and figures without text)."""
    if assets is None:
        return None
    out = []
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        found = texts.get(asset.get("name")) or {}
        out.append({**asset, "description": found.get("description"), "ocr_text": found.get("ocr_text")})
    return out


def dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False)
