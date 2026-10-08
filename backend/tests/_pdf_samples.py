"""
Tiny PDFs written by hand for the image-asset tests (no reportlab in the images).

- `text_and_image_pdf()`: one page with a line of text and an embedded raster
  image (an RGB XObject, FlateDecode);
- `image_only_page()`: a page that is nothing but a raster image;
- `pdf(pages)`: any sequence of such pages in one document.

Every image is a deterministic gradient, so its PNG (and sha256) is stable.
"""
import zlib

PAGE_W, PAGE_H = 612, 792


def _rgb(width: int, height: int, seed: int) -> bytes:
    out = bytearray()
    for y in range(height):
        for x in range(width):
            out += bytes(((x * 7 + seed * 40) % 256, (y * 5 + seed * 90) % 256, ((x + y) * 3 + seed * 13) % 256))
    return bytes(out)


def text_page(text: str, image=None):
    """A page with `text` near the top and, optionally, `image` = (w, h, seed, x, y, draw_w, draw_h)."""
    return {"text": text, "image": image}


def image_only_page(seed: int = 3, width: int = 300, height: int = 400):
    return {"text": None, "image": (width, height, seed, 0, 0, PAGE_W, PAGE_H)}


def pdf(pages) -> bytes:
    objects = []  # index -> bytes (object body)

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    pages_ref = add(b"")  # filled below
    page_refs = []
    for page in pages:
        content = b""
        resources = b"<< /Font << /F1 %d 0 R >>" % font
        if page.get("image"):
            w, h, seed, x, y, dw, dh = page["image"]
            data = zlib.compress(_rgb(w, h, seed))
            image = add(b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceRGB "
                        b"/BitsPerComponent 8 /Filter /FlateDecode /Length %d >>\nstream\n" % (w, h, len(data))
                        + data + b"\nendstream")
            resources += b" /XObject << /Im1 %d 0 R >>" % image
            content += b"q %d 0 0 %d %d %d cm /Im1 Do Q\n" % (dw, dh, x, y)
        resources += b" >>"
        if page.get("text"):
            content += b"BT /F1 18 Tf 72 720 Td (%s) Tj ET\n" % page["text"].encode("latin-1")
        stream = add(b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream")
        page_refs.append(add(b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %d %d] /Resources %s /Contents %d 0 R >>"
                             % (pages_ref, PAGE_W, PAGE_H, resources, stream)))
    objects[pages_ref - 1] = (b"<< /Type /Pages /Kids [" + b" ".join(b"%d 0 R" % r for r in page_refs)
                              + b"] /Count %d >>" % len(page_refs))
    catalog = add(b"<< /Type /Catalog /Pages %d 0 R >>" % pages_ref)

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, catalog, xref)
    return bytes(out)


def text_and_image_pdf() -> bytes:
    """One page: a heading and a 200x150 raster image drawn at (100, 300), 300x225 pt."""
    return pdf([text_page("Curso de exemplo - pagina um", image=(200, 150, 1, 100, 300, 300, 225))])


def course_pdf() -> bytes:
    """Three pages: text + image, image only, text only."""
    return pdf([
        text_page("Curso de exemplo - pagina um", image=(200, 150, 1, 100, 300, 300, 225)),
        image_only_page(seed=2),
        text_page("Pagina tres so com texto"),
    ])
