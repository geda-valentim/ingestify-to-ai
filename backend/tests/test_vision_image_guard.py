"""
The decompression-bomb guard in `Florence2Describer._open_image`.

Why this file exists
--------------------
The 10MB byte limit the API enforces protects nothing on its own. A 10MB PNG is
allowed to declare a 60000x60000 canvas and expand to tens of gigabytes of
pixels the moment something calls `Image.open(...).convert("RGB")` - which is
the most obvious denial-of-service these endpoints have, and the only place it
is stopped is the worker, where PIL lives.

`test_images_endpoints.py` used to "cover" this by handing the API a canned
`{"error_code": "IMAGE_TOO_LARGE", "http_status": 422}` dict and checking the
API relayed it. That is the generic structured-failure relay - already
parametrized over four other codes in the same file - and it never touched
`_open_image`, `max_image_pixels` or `PIL.Image.MAX_IMAGE_PIXELS`. Deleting the
guard entirely left that test green.

So these tests drive the guard itself, with real PIL and real image files. They
need no torch: `_open_image` takes the backend as an argument, and only its
`image_module` is used.

The two rungs are tested separately because they fire at different moments and
a mutation can remove either one alone:

  * PIL's own guard raises inside `open()`, but only past *twice*
    MAX_IMAGE_PIXELS - that is how Pillow is written (warn at 1x, raise at 2x).
  * The explicit `width * height > max_image_pixels` re-check is what covers
    the band between 1x and 2x, where PIL merely warns and would otherwise hand
    the model an image the operator has forbidden.
"""

from pathlib import Path

import pytest

from workers.vision.errors import (
    VisionImageTooLargeError,
    VisionInferenceError,
    VisionInvalidImageError,
)
from workers.vision.florence2_describer import Florence2Describer, _Florence2Backend

PIL_Image = pytest.importorskip(
    "PIL.Image",
    reason="Pillow is a real project dependency (backend/requirements-vision.txt); "
    "the pixel-bomb guard cannot be tested without the library it guards.",
)


@pytest.fixture
def pil_backend():
    """The real PIL, wrapped in the backend object `_open_image` expects.

    `MAX_IMAGE_PIXELS` is a module global that `_open_image` writes to, so it
    is saved and restored: leaking a tiny limit into the rest of the suite
    would turn every later `Image.open` into a bomb error.
    """
    original = PIL_Image.MAX_IMAGE_PIXELS
    try:
        # torch / processor / model are genuinely unused by _open_image; passing
        # a mock here would only hide it if that ever stopped being true.
        yield _Florence2Backend(
            torch=None, image_module=PIL_Image, auto_processor=None, model_cls=None
        )
    finally:
        PIL_Image.MAX_IMAGE_PIXELS = original


@pytest.fixture
def describer():
    def _make(max_image_pixels):
        return Florence2Describer(
            model_id="florence-community/Florence-2-base-ft",
            revision="0b03b6f15a4a211370fb204aee4e7dd48887ea37",
            device="cpu",
            dtype="float32",
            cache_dir="/models/huggingface",
            max_image_pixels=max_image_pixels,
        )

    return _make


@pytest.fixture
def png(tmp_path):
    """Write a real PNG of the given size. Small on disk, honest in its header."""

    def _make(width, height, name="image.png"):
        path = tmp_path / name
        PIL_Image.new("RGB", (width, height), (12, 34, 56)).save(path)
        return path

    return _make


class TestPixelLimit:
    @pytest.mark.filterwarnings("ignore::PIL.Image.DecompressionBombWarning")
    def test_an_image_over_the_pixel_limit_is_rejected(self, describer, pil_backend, png):
        """
        40x40 = 1600 pixels against a 1200 limit: over the limit, but under
        Pillow's own 2x raise threshold, so the explicit re-check is the ONLY
        thing standing between this image and `convert("RGB")`.
        """
        path = png(40, 40)

        with pytest.raises(VisionImageTooLargeError) as exc_info:
            describer(max_image_pixels=1200)._open_image(path, pil_backend)

        message = str(exc_info.value)
        assert "40x40" in message and "1600" in message
        assert "VISION_MAX_IMAGE_PIXELS" in message
        assert exc_info.value.http_status == 422
        assert exc_info.value.error_code == "IMAGE_TOO_LARGE"

    def test_pils_own_bomb_guard_is_armed_with_our_limit(self, describer, pil_backend, png):
        """
        16x over the limit: Pillow raises inside `open()`, before the size is
        ever read, and that exception has to become the same typed error rather
        than a generic "could not decode".

        Distinguished from the test above by the wording - "exceeds the N pixel
        limit" is only reachable through the DecompressionBomb branch - so this
        also pins that `MAX_IMAGE_PIXELS` is actually being set from config.
        """
        path = png(40, 40)

        with pytest.raises(VisionImageTooLargeError) as exc_info:
            describer(max_image_pixels=100)._open_image(path, pil_backend)

        assert "exceeds the 100 pixel limit" in str(exc_info.value)
        assert exc_info.value.http_status == 422

    def test_the_limit_reaches_pil_as_the_configured_value(
        self, describer, pil_backend, png
    ):
        """The guard is configured, not hardcoded: PIL is armed with our number."""
        describer(max_image_pixels=1200)._open_image(png(10, 10), pil_backend)

        assert PIL_Image.MAX_IMAGE_PIXELS == 1200

    def test_an_image_within_the_limit_is_opened_and_converted(
        self, describer, pil_backend, png
    ):
        """A guard that rejects everything is not a guard."""
        image, width, height = describer(max_image_pixels=50_000_000)._open_image(
            png(40, 30), pil_backend
        )

        try:
            assert (width, height) == (40, 30)
            # RGB, always: Florence-2 cannot take a palette or an alpha channel.
            assert image.mode == "RGB"
            assert image.size == (40, 30)
        finally:
            image.close()

    def test_an_exactly_at_the_limit_image_is_allowed(self, describer, pil_backend, png):
        """The comparison is strictly greater-than; the documented limit is inclusive."""
        image, _, _ = describer(max_image_pixels=1600)._open_image(png(40, 40), pil_backend)
        image.close()


class TestOtherOpenFailures:
    """The bomb branch must not swallow the two other ways `open()` fails."""

    def test_a_file_that_is_not_an_image_is_an_invalid_image(
        self, describer, pil_backend, tmp_path
    ):
        path = tmp_path / "not-an-image.png"
        path.write_bytes(b"#!/bin/sh\nrm -rf /\n")

        with pytest.raises(VisionInvalidImageError) as exc_info:
            describer(max_image_pixels=50_000_000)._open_image(path, pil_backend)

        assert exc_info.value.http_status == 422
        assert exc_info.value.error_code == "UNSUPPORTED_IMAGE_FORMAT"

    def test_a_missing_file_names_the_mount_that_is_probably_wrong(
        self, describer, pil_backend, tmp_path
    ):
        """
        The API writes the image and the worker reads it back off a shared
        volume, so "file not found" here is almost always a missing bind mount -
        and an operator should not have to work that out from a PIL traceback.
        """
        missing = Path(tmp_path) / "never-written.png"

        with pytest.raises(VisionInferenceError) as exc_info:
            describer(max_image_pixels=50_000_000)._open_image(missing, pil_backend)

        assert "/tmp/ingestify" in str(exc_info.value)
