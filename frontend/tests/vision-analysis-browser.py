#!/usr/bin/env python3
"""Exercise every catalog task, conditional inputs, generation and result geometry."""
import argparse
import base64
import json
from email.parser import BytesParser
from email.policy import default
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, expect

JOB = "55555555-5555-4555-8555-555555555555"
USER = {"id": "vision-test", "username": "vision-test", "email": "vision@example.test",
        "is_active": True, "is_admin": False, "created_at": "2026-10-06T00:00:00"}
PROJECT = {"id": "vision-project", "name": "Vision checks", "archived": False, "folders": []}
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
CORS = {"access-control-allow-origin": "*", "access-control-allow-headers": "*"}
SCHEMA = json.loads((Path(__file__).resolve().parents[1] / "docs/doc2md_openapi.json").read_text())
TASKS = SCHEMA["components"]["schemas"]["ImageAnalyzeOptions"]["properties"]["task"]["x-task-catalog"]
GENERATION = SCHEMA["components"]["schemas"]["VisionGenerationOptions"]


def check(browser, url, task):
    context = browser.new_context(viewport={"width": 1440, "height": 1100})
    auth = json.dumps({"state": {"user": USER, "token": "synthetic-vision-token"}, "version": 0})
    context.add_init_script("localStorage.setItem('auth-storage', " + json.dumps(auth) + ");")
    page = context.new_page()
    captured, errors = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    geometry = []
    if task["output"] in ("boxes", "mixed"):
        geometry.append({"label": "VISION_OBJECT", "bbox": [0.1, 0.1, 0.9, 0.9], "polygons": []})
    if task["output"] == "ocr":
        geometry.append({"label": "VISION_TEXT", "quad_box": [0, 0, 1, 0, 1, 1, 0, 1], "bbox": [0, 0, 1, 1], "polygons": []})
    if task["output"] in ("polygons", "mixed"):
        geometry.append({"label": "VISION_MASK", "polygons": [[0, 0, 1, 0, 1, 1, 0, 1]]})
    image = {"operation": "analyze", "task": task["task"], "task_label": task["label"],
             "image_base64": base64.b64encode(PNG).decode(), "image_mime_type": "image/png",
             "width": 1, "height": 1, "text": "VISION_RESULT", "lines": [], "regions": geometry,
             "model": {"model_id": "fixture", "revision": "fixture", "device": "cpu", "dtype": "float32"}, "duration_ms": 1}

    def intercept(route):
        request = route.request
        if request.resource_type not in ("fetch", "xhr") or request.headers.get("rsc") == "1":
            return route.continue_()
        if request.method == "OPTIONS":
            return route.fulfill(status=204, headers=CORS)
        path = urlparse(request.url).path.removeprefix("/api")
        value = None
        if path == "/auth/me": value = USER
        elif path == "/projects": value = {"projects": [PROJECT]}
        elif path == "/datalakes": value = {"connections": []}
        elif path == "/images/capabilities":
            value = {"enabled": True, "dependencies_installed": True, "model_downloaded": True,
                     "caption_tasks": ["<CAPTION>", "<DETAILED_CAPTION>", "<MORE_DETAILED_CAPTION>"],
                     "default_caption_task": "<MORE_DETAILED_CAPTION>", "max_image_size_mb": 10,
                     "tasks": TASKS, "generation_schema": GENERATION,
                     "generation_defaults": {"max_new_tokens": 1024, "num_beams": 3}}
        elif path == "/images/analyze/upload":
            message = BytesParser(policy=default).parsebytes(b"Content-Type: " + request.headers["content-type"].encode() + b"\r\n\r\n" + request.post_data_buffer)
            parts = {part.get_param("name", header="content-disposition"): part.get_payload(decode=True) for part in message.iter_parts()}
            assert parts["task"].decode() == task["task"]
            assert parts["wait"] == b"false" and parts["file"] == PNG
            assert json.loads(parts["generation"]) == {"max_new_tokens": 64, "num_beams": 1}
            allowed = {"task", "wait", "file", "project_id", "generation"}
            if task["input"] == "text":
                assert parts["text_input"] == b"a red car"
                allowed.add("text_input")
            elif task["input"] == "region":
                region = json.loads(parts["region"])
                assert len(region) == 4 and all(0 <= coordinate <= 1 for coordinate in region)
                assert abs(region[0] - 0.2) < 0.02 and abs(region[3] - 0.75) < 0.02
                allowed.add("region")
            assert set(parts) == allowed
            captured.append(parts)
            image["request"] = {"task": task["task"], "text_input": "a red car" if task["input"] == "text" else None,
                                "region": json.loads(parts["region"]) if "region" in parts else None,
                                "generation": json.loads(parts["generation"])}
            return route.fulfill(status=202, json={"job_id": JOB, "status": "queued", "project": PROJECT}, headers=CORS)
        elif path == f"/jobs/{JOB}":
            value = {"job_id": JOB, "type": "main", "kind": "image", "status": "completed", "progress": 100,
                     "name": "image.png", "tags": [], "created_at": "2026-10-06T00:00:00", "project": PROJECT}
        elif path == f"/jobs/{JOB}/pages":
            value = {"job_id": JOB, "total_pages": 0, "pages_completed": 0, "pages_failed": 0, "pages": []}
        elif path == f"/jobs/{JOB}/result":
            value = {"job_id": JOB, "status": "completed", "type": "main", "completed_at": "2026-10-06T00:00:00",
                     "result": {"markdown": "VISION_RESULT", "metadata": {"format": "png", "size_bytes": len(PNG)}, "image": image}}
        if value is None:
            return route.fulfill(status=404, json={"detail": "Unavailable in fixture"}, headers=CORS)
        route.fulfill(json=value, headers=CORS)

    page.route("**/*", intercept)
    try:
        page.goto(url.rstrip("/") + "/convert?project_id=" + PROJECT["id"])
        page.locator('input[type="file"]').set_input_files({"name": "image.png", "mimeType": "image/png", "buffer": PNG})
        page.get_by_label("Processamento da imagem").select_option("analyze")
        selection = page.get_by_label("Tarefa de visão")
        expect(selection.locator("option")).to_have_count(15)
        selection.select_option(task["task"])
        submit = page.get_by_role("button", name="Processar arquivo", exact=True)
        if task["input"] != "none": expect(submit).to_be_disabled()
        if task["input"] == "text":
            page.get_by_label("Texto para localizar na imagem").fill("a red car")
        elif task["input"] == "region":
            picker = page.locator('svg[aria-label="Selecionar região"]')
            expect(picker).to_be_visible()
            box = picker.bounding_box()
            page.mouse.move(box["x"] + box["width"] * .2, box["y"] + box["height"] * .25)
            page.mouse.down()
            page.mouse.move(box["x"] + box["width"] * .65, box["y"] + box["height"] * .75, steps=5)
            page.mouse.up()
        page.get_by_text("Opções de geração", exact=True).click()
        page.get_by_label("Max New Tokens").fill("64")
        page.get_by_label("Num Beams").fill("1")
        expect(submit).to_be_enabled()
        submit.click()
        page.wait_for_url("**/jobs/" + JOB, timeout=45000)
        expect(page.get_by_role("heading", name="Análise da imagem", level=2)).to_be_visible()
        expect(page.get_by_alt_text("Imagem enviada")).to_be_visible()
        expect(page.get_by_role("heading", name=task["label"], level=3)).to_be_visible()
        expect(page.locator('svg[aria-label="Regiões detectadas"] g')).to_have_count(len(geometry))
        assert len(captured) == 1
        page.reload()
        expect(page.get_by_role("heading", name="Análise da imagem", level=2)).to_be_visible()
        expect(page.locator('svg[aria-label="Regiões detectadas"] g')).to_have_count(len(geometry))
        assert not errors, errors
        print("PASS: front task " + task["task"] + ", input, generation, geometry and F5", flush=True)
    finally:
        context.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:3001")
    parser.add_argument("--chromium")
    args = parser.parse_args()
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=args.chromium, headless=True, args=["--no-sandbox"])
        try:
            for task in TASKS: check(browser, args.url, task)
        finally:
            browser.close()
