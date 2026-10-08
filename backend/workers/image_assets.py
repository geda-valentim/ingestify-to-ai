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
    public_asset,
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
    bytes are stored (`count_limit` / `size_limit`); a split PDF's merge applies the
    same limits across its pages.
    """

    def __init__(self, job_id: str, storage_factory: Callable, *, page_offset: int = 0, settings=None):
        if settings is None:
            from shared.config import get_settings

            settings = get_settings()
        self.job_id = str(job_id)
        self.page_offset = int(page_offset or 0)
        self.min_px = int(settings.conversion_asset_min_px)
        self.max_count = int(settings.conversion_asset_max_count)
        self.max_bytes = int(settings.conversion_asset_max_total_mb) * 1024 * 1024
        self.page_dpi = int(settings.conversion_page_image_dpi)
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

    def _store(self, image, *, kind: str, page: Optional[int], position: int, bbox=None,
               index: int = 0) -> Optional[dict]:
        if image is None:
            self.skipped["unavailable"] += 1
            return None
        width, height = image.size
        if kind == KIND_PICTURE and (width < self.min_px or height < self.min_px):
            self.skipped["too_small"] += 1
            return None
        data = encode_png(image)
        if len(self.assets) + 1 > self.max_count:
            self.skipped["count_limit"] += 1
            return None
        if self.total_bytes + len(data) > self.max_bytes:
            self.skipped["size_limit"] += 1
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
            "position": position,
        }
        self.assets.append(asset)
        self.total_bytes += len(data)
        return asset

    def add_picture(self, image, *, page: Optional[int], index: int, bbox=None) -> Optional[dict]:
        return self._store(image, kind=KIND_PICTURE, page=page, position=index, bbox=bbox, index=index)

    def add_page(self, image, *, page: int) -> Optional[dict]:
        return self._store(image, kind=KIND_PAGE, page=page, position=0)

    def ordered(self) -> list:
        return sorted(self.assets, key=sort_key)

    def result_fields(self, *, public: bool = False) -> dict:
        assets = self.ordered()
        return {"assets": [public_asset(a) for a in assets] if public else assets,
                "assets_skipped": dict(self.skipped)}


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


def extract_pictures(doc, collector: AssetCollector) -> str:
    """
    Store every picture of `doc` (docling_core DoclingDocument) and return its
    markdown with the stored pictures referenced by asset URL, in document order.

    Every picture the export could embed ends with either our URL or no image at
    all (placeholder): never a `data:` URI in the markdown.
    """
    from docling_core.types.doc import ImageRef, ImageRefMode, PictureItem

    handled = set()
    per_page = {}
    for item, _level in doc.iterate_items():
        if not isinstance(item, PictureItem):
            continue
        handled.add(id(item))
        prov = item.prov[0] if item.prov else None
        page = collector.absolute_page(prov.page_no if prov else None)
        per_page[page] = per_page.get(page, 0) + 1
        try:
            image = item.get_image(doc)
        except Exception as e:  # noqa: BLE001 - counted as unavailable
            logger.warning(f"Could not read a picture of page {page}: {e}")
            image = None
        asset = collector.add_picture(image, page=page, index=per_page[page],
                                      bbox=_bbox(doc, prov) if prov else None)
        if asset is None:
            item.image = None  # the export writes the placeholder
            continue
        if item.image is None:
            item.image = ImageRef.from_pil(image, dpi=72)
        item.image.uri = Path(asset["url"])
    for item in getattr(doc, "pictures", None) or []:
        if id(item) not in handled:
            item.image = None
    return doc.export_to_markdown(image_mode=ImageRefMode.REFERENCED)


def render_pages(pdf_path: Path, collector: AssetCollector) -> int:
    """Render every page of a PDF to a PNG asset (kind "page"). Returns how many were stored."""
    import pypdfium2 as pdfium

    stored = 0
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        for index in range(len(pdf)):
            page = pdf[index]
            try:
                image = page.render(scale=collector.page_dpi / 72.0).to_pil()
            finally:
                page.close()
            if collector.add_page(image, page=collector.absolute_page(index + 1)) is not None:
                stored += 1
    finally:
        pdf.close()
    return stored
