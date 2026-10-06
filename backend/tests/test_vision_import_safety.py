"""
The vision package must be free to import.

`workers/celery_app.py` imports `workers.vision_tasks` unconditionally, in every
process: the API, celery beat, and the general worker. If any of that pulled in
torch, all three would pay for a dependency they never use - and on a laptop
with no GPU and no vision extra installed, they would fail outright.

These tests pin that property down rather than trusting it, because it is the
kind of guarantee a single convenience import at the top of a module silently
destroys.
"""

import builtins
import importlib
import sys
import subprocess
from pathlib import Path

import pytest

VISION_MODULES = [
    "workers.vision",
    "workers.vision.base_describer",
    "workers.vision.errors",
    "workers.vision.factory",
    "workers.vision.florence2_describer",
    "workers.vision.stub_describer",
    "workers.vision.image_input",
    "workers.vision.download",
    "workers.vision_tasks",
]

HEAVY_MODULES = ("torch", "transformers", "PIL", "huggingface_hub")


def isolated_import_check(module_names, block=False):
    # Celery decorators register tasks process-wide; sys.modules restoration
    # cannot undo those registrations safely in a shared pytest process.
    script = """
import builtins, importlib, sys
modules = %r
heavy = %r
real_import = builtins.__import__
def blocking_import(name, *args, **kwargs):
    if name.split('.')[0] in heavy:
        raise ImportError(name + ' blocked by import probe')
    return real_import(name, *args, **kwargs)
if %r:
    builtins.__import__ = blocking_import
for name in modules:
    importlib.import_module(name)
assert not any(name in sys.modules for name in heavy)
""" % (module_names, HEAVY_MODULES, block)
    result = subprocess.run([sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.fixture(autouse=True)
def restore_import_state():
    """Import probes must not replace classes/Pillow plugin state for later tests."""
    def tracked(name):
        return name in VISION_MODULES or name == "api.image_routes" or name.split(".")[0] in HEAVY_MODULES
    modules = {name: module for name, module in sys.modules.items() if tracked(name)}
    parents = {name: dict(sys.modules[name].__dict__) for name in ("workers", "workers.vision", "api", "PIL") if name in sys.modules}
    yield
    for name in list(sys.modules):
        if tracked(name) and name not in modules:
            sys.modules.pop(name, None)
    sys.modules.update(modules)
    for name, attributes in parents.items():
        if name in sys.modules:
            sys.modules[name].__dict__.clear()
            sys.modules[name].__dict__.update(attributes)


@pytest.mark.parametrize("module_name", VISION_MODULES)
def test_module_imports_without_torch(module_name, monkeypatch):
    """Every module imports even when `import torch` is guaranteed to fail.

    The blocker below raises for torch and friends no matter what is installed,
    so this test proves the property on a developer machine that happens to have
    the vision extra as well as in CI, where it does not.
    """
    if module_name == "workers.vision_tasks":
        isolated_import_check([module_name], block=True)
        return
    real_import = builtins.__import__

    def blocking_import(name, *args, **kwargs):
        root = name.split(".")[0]
        if root in HEAVY_MODULES:
            raise ImportError(f"{root} is blocked by this test")
        return real_import(name, *args, **kwargs)

    for name in list(sys.modules):
        if name.split(".")[0] in HEAVY_MODULES:
            monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.delitem(sys.modules, module_name, raising=False)
    monkeypatch.setattr(builtins, "__import__", blocking_import)

    module = importlib.import_module(module_name)

    assert module is not None


def test_the_image_routes_module_imports_without_torch(monkeypatch):
    """The API shares the worker's image-input rules, and that must stay free.

    `api/image_routes.py` imports `workers.vision.image_input` so that decode,
    size limit and magic-byte sniffing have exactly one implementation instead
    of one per process. That import crosses from the API into the worker
    package, which is the sort of edge along which a torch dependency travels:
    the API image runs no model, and nobody would notice it had grown one until
    the container was 2.5GB heavier.
    """
    real_import = builtins.__import__

    def blocking_import(name, *args, **kwargs):
        root = name.split(".")[0]
        if root in HEAVY_MODULES:
            raise ImportError(f"{root} is blocked by this test")
        return real_import(name, *args, **kwargs)

    for name in list(sys.modules):
        if name.split(".")[0] in HEAVY_MODULES:
            monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.delitem(sys.modules, "api.image_routes", raising=False)
    monkeypatch.setattr(builtins, "__import__", blocking_import)

    module = importlib.import_module("api.image_routes")

    # And the shared rule really is the one in use, not a private copy that
    # drifted back in: tolerating the newlines every command-line base64
    # encoder emits is behaviour only `image_input` has.
    wrapped = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8\n"
        "z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==\n"
    )
    assert module._decode_base64_image(wrapped).startswith(b"\x89PNG")
    assert module._validate_image_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8) == "image/png"


def test_importing_the_package_pulls_in_no_heavy_dependency():
    """Importing is not merely possible - it must also be free."""
    isolated_import_check(VISION_MODULES)


def test_constructing_a_describer_loads_nothing():
    """Construction stores strings. Weights arrive only when load() is called."""
    from workers.vision.florence2_describer import Florence2Describer

    describer = Florence2Describer(
        model_id="florence-community/Florence-2-base-ft",
        revision="0b03b6f15a4a211370fb204aee4e7dd48887ea37",
        device="cpu",
        dtype="float32",
        cache_dir="/models/huggingface",
    )

    assert describer.is_loaded is False
    assert "torch" not in sys.modules
    # info() is the capabilities path: it must answer without loading either.
    assert describer.info() == {
        "model_id": "florence-community/Florence-2-base-ft",
        "revision": "0b03b6f15a4a211370fb204aee4e7dd48887ea37",
        "device": "cpu",
        "dtype": "float32",
        "loaded": False,
    }


class TestTaskRegistration:
    """A vision task that is not registered under its exact name loops forever.

    With `task_acks_late=True` and `task_reject_on_worker_lost=True`, a
    NotRegistered message is redelivered indefinitely instead of failing once,
    so the names and the routing are worth asserting.
    """

    def test_tasks_are_registered_under_explicit_dotted_names(self):
        from workers.celery_app import celery_app

        import workers.vision_tasks  # noqa: F401

        for name in (
            "workers.vision_tasks.describe_image_task",
            "workers.vision_tasks.ocr_image_task",
            "workers.vision_tasks.vision_capabilities_task",
        ):
            assert name in celery_app.tasks

    def test_vision_tasks_route_to_their_own_queue(self):
        """The sync path cannot queue behind multi-minute PDF page jobs."""
        from shared.config import get_settings
        from workers.celery_app import celery_app

        routes = celery_app.conf.task_routes
        assert routes["workers.vision_tasks.*"] == {
            "queue": get_settings().vision_queue
        }

    def test_tasks_do_not_retry(self):
        """A retry cannot help a caller holding a connection open."""
        from workers.vision_tasks import describe_image_task, ocr_image_task

        assert describe_image_task.max_retries == 0
        assert ocr_image_task.max_retries == 0

    def test_task_timeout_outlives_the_request_deadline(self):
        """This is what makes the 504-then-poll fallback real work, not a promise."""
        from shared.config import get_settings
        from workers.vision_tasks import describe_image_task

        settings = get_settings()
        assert describe_image_task.time_limit == settings.vision_task_timeout_seconds
        assert describe_image_task.time_limit > settings.vision_request_timeout_seconds
        assert describe_image_task.soft_time_limit < describe_image_task.time_limit
