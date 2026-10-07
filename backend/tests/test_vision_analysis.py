"""Run real prompt assembly and generation dispatch without model dependencies."""
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from shared.vision_capabilities import VISION_TASKS
from shared.vision_outputs import normalize_output
from workers.vision.florence2_describer import Florence2Describer


@pytest.mark.parametrize("task", list(VISION_TASKS))
def test_generation_parses_the_task_token_instead_of_the_full_prompt(monkeypatch, task):
    calls = {}
    model = Florence2Describer("fixture", "rev", "cpu", "float32", "/unused")
    monkeypatch.setattr(model, "load", lambda: None)
    monkeypatch.setattr(model, "_open_image", lambda *args: (object(), 100, 80))
    class Inputs(dict):
        def to(self, *args):
            return self
    class Processor:
        def __call__(self, **kwargs):
            calls["prompt"] = kwargs["text"]
            return Inputs(pixel_values="fixture")
        def batch_decode(self, *args, **kwargs):
            return ["decoded"]
        def post_process_generation(self, *args, **kwargs):
            calls["parsed_task"] = kwargs["task"]
            assert kwargs["image_size"] == (100, 80)
            return {task: "result"}
    def generate(**kwargs):
        calls["generation"] = kwargs
        return [1]
    model._processor = Processor()
    model._model = SimpleNamespace(generate=generate)
    model._backend = SimpleNamespace(torch=SimpleNamespace(inference_mode=nullcontext))
    request = {"task": task, "generation": {"max_new_tokens": 64, "num_beams": 1}}
    input_kind = VISION_TASKS[task][2]
    if input_kind == "text":
        request["text_input"] = "a green car"
    elif input_kind == "region":
        request["region"] = [0, 0.25, 0.75, 1]
    result = model.analyze("unused.png", request)
    assert calls["parsed_task"] == task
    assert calls["prompt"] == task + ("a green car" if input_kind == "text" else "<loc_0><loc_250><loc_750><loc_999>" if input_kind == "region" else "")
    assert calls["generation"]["max_new_tokens"] == 64
    assert calls["generation"]["num_beams"] == 1
    assert "temperature" not in calls["generation"]
    assert result["task"] == task and result["output"] == "result"


def test_mixed_output_preserves_box_and_polygon_labels():
    text, regions, lines = normalize_output({
        "bboxes": [[1, 2, 3, 4]], "bboxes_labels": ["car"],
        "polygons": [[[1, 2, 3, 4, 5, 6], [2, 3, 4, 5, 6, 7]]], "polygons_labels": ["road"],
    })
    assert text == "car\nroad"
    assert regions[0]["bbox"] == [1, 2, 3, 4]
    assert len(regions[1]["polygons"]) == 2
    assert not lines


def test_invalid_geometry_does_not_fabricate_a_region():
    text, regions, lines = normalize_output({"bboxes": [[1, 2, 3], [0, float("nan"), 2, 3]],
        "quad_boxes": [[]], "polygons": [[[]]], "labels": ["invalid"]})
    assert (text, regions, lines) == ("", [], [])


@pytest.mark.parametrize("hook", ["_start_vision_heartbeat", "_preload_vision_model"])
def test_child_init_returns_while_expensive_probe_or_preload_runs(monkeypatch, hook):
    import threading
    import time
    from workers import vision_tasks
    entered, release = threading.Event(), threading.Event()
    def slow():
        entered.set()
        release.wait(timeout=3)
    monkeypatch.setattr(vision_tasks, "consumes_vision_queue", lambda: True)
    monkeypatch.setattr(vision_tasks.settings, "vision_preload_model", True)
    # _preload_vision_model reads get_settings(), which differs from the module's
    # `settings` once another test cleared the settings cache (order-dependent).
    from shared.config import get_settings
    monkeypatch.setattr(get_settings(), "vision_preload_model", True)
    monkeypatch.setattr(vision_tasks, "start_vision_heartbeat", slow)
    monkeypatch.setattr(vision_tasks, "get_image_describer", lambda: SimpleNamespace(load=slow))
    try:
        started = time.monotonic()
        getattr(vision_tasks, hook)()
        assert time.monotonic() - started < 1
        assert entered.wait(timeout=1)
    finally:
        release.set()


def test_non_vision_workers_do_not_preload_the_model(monkeypatch):
    from workers import vision_tasks
    monkeypatch.setattr(vision_tasks, "consumes_vision_queue", lambda: False)
    monkeypatch.setattr(vision_tasks.settings, "vision_preload_model", True)
    def no_model():
        raise AssertionError("A document/audio worker must not load the vision model")
    monkeypatch.setattr(vision_tasks, "get_image_describer", no_model)
    vision_tasks._preload_vision_model()


@pytest.mark.parametrize('tokens, eos, finish', [([2,17,2], True, 'stop'), ([2,17,17], False, 'length')])
def test_full_generation_reuses_bitmap_and_reports_eos_or_truncation(monkeypatch, tokens, eos, finish):
    import sys
    class Criteria: pass
    monkeypatch.setitem(sys.modules, 'transformers', SimpleNamespace(StoppingCriteria=Criteria, StoppingCriteriaList=list))
    model = Florence2Describer('fixture', 'rev', 'cpu', 'float32', '/unused')
    monkeypatch.setattr(model, 'load', lambda: None)
    monkeypatch.setattr(model, '_open_image', lambda *args: (_ for _ in ()).throw(AssertionError('Bitmap was decoded twice')))
    bitmap = SimpleNamespace(size=(100,80))
    class Inputs(dict):
        def to(self, *args): return self
    class Processor:
        def __call__(self, **kwargs):
            assert kwargs['images'] is bitmap
            return Inputs(pixel_values='fixture')
        def batch_decode(self, *args, **kwargs): return ['decoded']
        def post_process_generation(self, *args, **kwargs): return {'<CAPTION>':'result'}
    def generate(**kwargs):
        criteria = kwargs['stopping_criteria'][0]
        assert criteria(None, None) is False
        return [SimpleNamespace(tolist=lambda:tokens)]
    model._processor = Processor()
    model._model = SimpleNamespace(generate=generate, generation_config=SimpleNamespace(eos_token_id=2))
    model._backend = SimpleNamespace(torch=SimpleNamespace(inference_mode=nullcontext))
    model._full_context = {'image':bitmap, 'check':lambda:True}
    output = model.analyze('unused.png', {'task':'<CAPTION>'})
    assert output['generation_metadata'] == {'generated_tokens':2, 'eos':eos, 'finish_reason':finish}
    assert output['truncated'] is (finish=='length')
