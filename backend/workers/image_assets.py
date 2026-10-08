"""
Extract the image assets of a document conversion (shared/conversion_assets.py).

- `extract_pictures(doc, collector)`: every PictureItem of a docling document,
  in document order, stored as a PNG; returns the markdown export in which each
  stored picture is referenced (`ImageRefMode.REFERENCED` with the picture's
  `image.uri` set to its asset URL) and each skipped one keeps docling's
  `<!-- image -->` placeholder;
- `render_pages(pdf_path, collector)`: every page of a PDF rendered to a PNG with
  pypdfium2 (installed with docling in the api and worker images).

Testable without docling's models: `extract_pictures` only needs a
`docling_core` DoclingDocument, which tests build directly.
"""
import hashlib
import io
import logging
import re
from pathlib import Path
from typing import Callable, Optional

from shared.conversion_assets import (
    ASSET_MIME,
    KIND_PAGE,
    KIND_PICTURE,
    asset_url,
    empty_skipped,
    object_name,
    page_name,
    picture_name,
    public_assets,
    slot_of,
    sort_key,
)

logger = logging.getLogger(__name__)


class AssetCollector:
    """
    The assets of one conversion run: a whole document, or one page job of a split
    PDF (`page_offset` = its page number - 1, so names and `page` are absolute).

    Always stored under the MAIN job id (`job_id`). Limits (settings): pictures
    under `CONVERSION_ASSET_MIN_PX` on either side are skipped (`too_small`), and
    at most `CONVERSION_ASSET_MAX_COUNT` assets / `CONVERSION_ASSET_MAX_TOTAL_MB`
    bytes are stored (`count_limit` / `size_limit`). The count and the bytes used
    so far are checked before an image is encoded, the encoded size before it is
    uploaded. A split PDF's page jobs also share `budget`
    (shared.conversion_assets.JobAssetBudget, the per-job reservation); the merge
    applies the limits across pages once more, as the authority.
    """

    def __init__(self, job_id: str, storage_factory: Callable, *, page_offset: int = 0, settings=None,
                 budget=None):
        if settings is None:
            from shared.config import get_settings

            settings = get_settings()
        self.job_id = str(job_id)
        self.page_offset = int(page_offset or 0)
        self.min_px = int(settings.conversion_asset_min_px)
        self.max_count = int(settings.conversion_asset_max_count)
        self.max_bytes = int(settings.conversion_asset_max_total_mb) * 1024 * 1024
        self.page_dpi = int(settings.conversion_page_image_dpi)
        self.budget = budget
        self._storage_factory = storage_factory
        self._storage = None
        self.assets = []
        self.skipped = empty_skipped()
        self.total_bytes = 0

    def absolute_page(self, local_page: Optional[int]) -> Optional[int]:
        return local_page + self.page_offset if local_page else None

    def _storage_client(self):
        if self._storage is None:
            self._storage = self._storage_factory()
        return self._storage

    def blocked(self, kind: str, page: Optional[int], index: int = 0) -> Optional[str]:
        """Why nothing more may be stored at this position (before any encoding), or None."""
        if len(self.assets) >= self.max_count:
            return "count_limit"
        if self.total_bytes >= self.max_bytes:
            return "size_limit"
        if self.budget is not None:
            allowed, reason = self.budget.precheck(slot_of(kind, page, index))
            if allowed is False:
                return reason
        return None

    def skip(self, reason: str) -> None:
        self.skipped[reason] += 1

    def _store(self, image, *, kind: str, page: Optional[int], bbox=None, index: int = 0) -> Optional[dict]:
        if image is None:
            self.skip("unavailable")
            return None
        width, height = image.size
        if kind == KIND_PICTURE and (width < self.min_px or height < self.min_px):
            self.skip("too_small")
            return None
        reason = self.blocked(kind, page, index)
        if reason:
            self.skip(reason)
            return None
        data = encode_png(image)
        if self.total_bytes + len(data) > self.max_bytes:
            self.skip("size_limit")
            return None
        if self.budget is not None:
            allowed, reason = self.budget.commit(slot_of(kind, page, index), len(data))
            if allowed is False:
                self.skip(reason)
                return None
        sha256 = hashlib.sha256(data).hexdigest()
        name = picture_name(page, index, sha256) if kind == KIND_PICTURE else page_name(page or 0, sha256)
        storage = self._storage_client()
        stored = storage.upload_file(bucket_name=storage.bucket_results, object_name=object_name(self.job_id, name),
                                     file_data=data, content_type=ASSET_MIME)
        if stored is False:
            raise RuntimeError(f"MinIO did not store {object_name(self.job_id, name)}")
        asset = {
            "name": name, "kind": kind, "page": page, "bbox": bbox, "sha256": sha256, "mime": ASSET_MIME,
            "width": width, "height": height, "size_bytes": len(data), "url": asset_url(self.job_id, name),
        }
        self.assets.append(asset)
        self.total_bytes += len(data)
        return asset

    def add_picture(self, image, *, page: Optional[int], index: int, bbox=None) -> Optional[dict]:
        return self._store(image, kind=KIND_PICTURE, page=page, bbox=bbox, index=index)

    def add_page(self, image, *, page: int) -> Optional[dict]:
        return self._store(image, kind=KIND_PAGE, page=page)

    def ordered(self) -> list:
        return sorted(self.assets, key=sort_key)

    def result_fields(self) -> dict:
        return {"assets": public_assets(self.assets), "assets_skipped": dict(self.skipped)}


def encode_png(image) -> bytes:
    """Deterministic PNG bytes of a PIL image (same pixels, same bytes, same sha256)."""
    if image.mode not in ("RGB", "RGBA", "L", "LA"):
        image = image.convert("RGBA" if "A" in image.mode else "RGB")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _bbox(doc, prov) -> Optional[dict]:
    """The picture's box in page coordinates (points), top-left origin."""
    try:
        page = doc.pages.get(prov.page_no) if getattr(doc, "pages", None) else None
        box = prov.bbox
        if page is not None and page.size is not None:
            box = box.to_top_left_origin(page_height=page.size.height)
        return {"l": round(box.l, 2), "t": round(box.t, 2), "r": round(box.r, 2), "b": round(box.b, 2),
                "coord_origin": getattr(box.coord_origin, "value", str(box.coord_origin)),
                "page_width": round(page.size.width, 2) if page is not None and page.size else None,
                "page_height": round(page.size.height, 2) if page is not None and page.size else None}
    except Exception as e:  # noqa: BLE001 - a picture without a usable box still is an asset
        logger.debug(f"No bbox for a picture: {e}")
        return None


class FigureCollector:
    """
    The figures of one conversion run that go through the vision worker
    (describe_images / ocr_images; shared/figure_descriptions.py): one entry per
    PictureItem, in document order.

    - `image_mode=referenced`: the figure is the stored asset (`from_asset`): its
      anchor is the asset URL, nothing more is stored;
    - `image_mode=none`: the PNG is stored in the temporary area
      `figures/{job_id}/` (`store`), once per distinct image of this run, at most
      CONVERSION_FIGURE_MAX_COUNT distinct images; its anchor is a marker the
      export writes where docling's placeholder was.

    Pictures under CONVERSION_ASSET_MIN_PX on either side, unreadable ones and
    those past the limit are entries with `skip` (they keep the placeholder).
    """

    def __init__(self, job_id: str, storage_factory: Callable, *, page_offset: int = 0, settings=None,
                 budget=None):
        if settings is None:
            from shared.config import get_settings

            settings = get_settings()
        self.job_id = str(job_id)
        self.page_offset = int(page_offset or 0)
        self.min_px = int(settings.conversion_asset_min_px)
        self.max_count = int(getattr(settings, "conversion_figure_max_count", 50))
        # A split PDF's page jobs share the document-wide cap (JobAssetBudget, namespace
        # "figures", slot = sha256), checked before each upload
        self.budget = budget
        self._storage_factory = storage_factory
        self._storage = None
        self.entries = []
        self._stored = {}  # sha256 -> object name

    def absolute_page(self, local_page: Optional[int]) -> Optional[int]:
        return local_page + self.page_offset if local_page else None

    def _storage_client(self):
        if self._storage is None:
            self._storage = self._storage_factory()
        return self._storage

    def _entry(self, name, page, sha256=None, obj=None, anchor=None, skip=None) -> dict:
        entry = {"name": name, "page": page, "sha256": sha256, "object": obj, "anchor": anchor, "skip": skip}
        self.entries.append(entry)
        return entry

    def from_asset(self, asset: dict) -> dict:
        from shared.conversion_assets import object_name as asset_object

        return self._entry(asset["name"], asset.get("page"), asset["sha256"],
                           asset_object(self.job_id, asset["name"]), asset["url"])

    def skipped(self, page: Optional[int], reason: str) -> dict:
        return self._entry(None, page, skip=reason)

    def store(self, image, *, page: Optional[int], index: int) -> dict:
        """image_mode=none: keep the PNG for the vision worker; the entry's anchor is its marker."""
        from shared.figure_descriptions import figure_object, marker

        if image is None:
            return self.skipped(page, "unavailable")
        width, height = image.size
        if width < self.min_px or height < self.min_px:
            return self.skipped(page, "too_small")
        data = encode_png(image)
        sha256 = hashlib.sha256(data).hexdigest()
        name = picture_name(page, index, sha256)
        obj = self._stored.get(sha256)
        if obj is None:
            if len(self._stored) >= self.max_count:
                return self.skipped(page, "count_limit")
            # One object per distinct image, named by its hash: the same image on
            # several pages of a split PDF is stored (and counted) once
            obj = figure_object(self.job_id, f"{sha256}.png")
            if self.budget is not None:
                if self.budget.has(sha256):
                    self._stored[sha256] = obj
                    return self._entry(name, page, sha256, obj, marker(name))
                allowed, _reason = self.budget.precheck(sha256)
                if allowed is not False:
                    allowed, _reason = self.budget.commit(sha256, len(data))
                if allowed is False:
                    return self.skipped(page, "count_limit")
            storage = self._storage_client()
            stored = storage.upload_file(bucket_name=storage.bucket_results, object_name=obj, file_data=data,
                                         content_type=ASSET_MIME)
            if stored is False:
                raise RuntimeError(f"MinIO did not store {obj}")
            self._stored[sha256] = obj
        return self._entry(name, page, sha256, obj, marker(name))

    def result_fields(self) -> dict:
        return {"figures": [dict(entry) for entry in self.entries]}


def _skip_reason(collector: AssetCollector, before: dict) -> str:
    for reason, count in collector.skipped.items():
        if count > before.get(reason, 0):
            return reason
    return "unavailable"


def extract_pictures(doc, collector: Optional[AssetCollector], figures: Optional[FigureCollector] = None) -> str:
    """
    Store every picture of `doc` (docling_core DoclingDocument) and return its
    markdown with the stored pictures referenced by asset URL, in document order.

    Every picture the export could embed ends with either our URL or no image at
    all (placeholder): never a `data:` URI in the markdown.

    `collector` None (image_mode=none) with `figures`: no asset is stored; each
    figure to describe gets a `<!-- figure:{name} -->` marker in place of the
    placeholder (shared/figure_descriptions.py), the others keep the placeholder.
    """
    from docling_core.types.doc import ImageRef, ImageRefMode, PictureItem

    from shared.figure_descriptions import MARKER_URI_PREFIX, marker

    pages_of = collector if collector is not None else figures
    handled = set()
    per_page = {}
    marked = []
    for item, _level in doc.iterate_items():
        if not isinstance(item, PictureItem):
            continue
        handled.add(id(item))
        prov = item.prov[0] if item.prov else None
        page = pages_of.absolute_page(prov.page_no if prov else None)
        per_page[page] = per_page.get(page, 0) + 1
        try:
            image = item.get_image(doc)
        except Exception as e:  # noqa: BLE001 - counted as unavailable
            logger.warning(f"Could not read a picture of page {page}: {e}")
            image = None
        if collector is not None:
            before = dict(collector.skipped)
            asset = collector.add_picture(image, page=page, index=per_page[page],
                                          bbox=_bbox(doc, prov) if prov else None)
            if figures is not None:
                if asset is not None:
                    figures.from_asset(asset)
                else:
                    figures.skipped(page, _skip_reason(collector, before))
            if asset is None:
                item.image = None  # the export writes the placeholder
                continue
            uri = asset["url"]
        else:
            entry = figures.store(image, page=page, index=per_page[page])
            if entry.get("skip"):
                item.image = None
                continue
            uri = MARKER_URI_PREFIX + entry["name"]
            marked.append(entry["name"])
        if item.image is None:
            item.image = ImageRef.from_pil(image, dpi=72)
        item.image.uri = Path(uri)
    for item in getattr(doc, "pictures", None) or []:
        if id(item) not in handled:
            item.image = None
    markdown = doc.export_to_markdown(image_mode=ImageRefMode.REFERENCED)
    for name in marked:
        markdown = re.sub(r"!\[[^\]]*\]\(" + re.escape(MARKER_URI_PREFIX + name) + r"\)", marker(name), markdown)
    return markdown


def render_pages(pdf_path: Path, collector: AssetCollector) -> int:
    """Render every page of a PDF to a PNG asset (kind "page"). Returns how many were stored."""
    import pypdfium2 as pdfium

    stored = 0
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        for index in range(len(pdf)):
            number = collector.absolute_page(index + 1)
            # Checked before rendering: once a limit is hit no page is rendered
            reason = collector.blocked(KIND_PAGE, number)
            if reason:
                collector.skip(reason)
                continue
            page = pdf[index]
            try:
                image = page.render(scale=collector.page_dpi / 72.0).to_pil()
            finally:
                page.close()
            if collector.add_page(image, page=number) is not None:
                stored += 1
    finally:
        pdf.close()
    return stored
