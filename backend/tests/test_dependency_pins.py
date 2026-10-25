"""
The docling pipeline and torch are pinned exactly (spec 0022 S0), so an image rebuild
cannot silently swap the conversion pipeline. Plain line parsing, no pip needed.
"""

import re
from importlib import metadata
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent

DOCLING = {
    "docling": "2.87.0",
    "docling-core": "2.104.0",
    "docling-parse": "5.11.0",
    "docling-ibm-models": "3.15.0",
}
TORCH = {"torch": "2.13.0", "torchvision": "0.28.0"}

_LINE = re.compile(r"^([A-Za-z0-9._-]+)(\[[^\]]*\])?\s*(==|>=|<=|~=|<|>|!=)\s*([^\s;#,]+)")


def _pins(filename):
    """name -> (operator, version) for the first spec of each requirement line."""
    out = {}
    for raw in (BACKEND / filename).read_text().splitlines():
        m = _LINE.match(raw.strip())
        if m:
            out[m.group(1).lower().replace("_", "-")] = (m.group(3), m.group(4))
    return out


def test_base_pins_docling_packages_exactly():
    pins = _pins("requirements-base.txt")
    for name, version in DOCLING.items():
        assert pins.get(name) == ("==", version), name


def test_base_does_not_name_torch():
    pins = _pins("requirements-base.txt")
    assert not {"torch", "torchvision"} & set(pins)


@pytest.mark.parametrize("filename", ["requirements-cpu.txt", "requirements-cuda.txt"])
def test_cpu_and_cuda_pin_same_torch(filename):
    pins = _pins(filename)
    for name, version in TORCH.items():
        assert pins.get(name) == ("==", version), (filename, name)


@pytest.mark.parametrize("name,version", {**DOCLING, **TORCH}.items())
def test_installed_version_matches_pin(name, version):
    try:
        installed = metadata.version(name)
    except metadata.PackageNotFoundError:
        pytest.skip(f"{name} not installed")
    assert installed.split("+")[0] == version
