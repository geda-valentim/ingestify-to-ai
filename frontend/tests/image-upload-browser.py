#!/usr/bin/env python3
"""Exercise image upload settings, configured job output, timeout and F5."""
import argparse
import base64
import json
from email.parser import BytesParser
from email.policy import default
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, expect

JOB = "44444444-4444-4444-8444-444444444444"
USER = {"id": "image-test", "username": "image-test", "email": "image@example.test",
        "is_active": True, "is_admin": False, "created_at": "2026-10-06T00:00:00"}
PROJECT = {"id": "image-project", "name": "Image checks", "archived": False, "folders": []}
TASKS = ["<CAPTION>", "<DETAILED_CAPTION>", "<MORE_DETAILED_CAPTION>"]
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
CORS = {"access-control-allow-origin": "*", "access-control-allow-headers": "*"}


def check(browser, url, operation, task=None, timeout=False):
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    auth = json.dumps({"state": {"user": USER, "token": "synthetic-image-token"}, "version": 0})
    context.add_init_script("localStorage.setItem('auth-storage', " + json.dumps(auth) + ");")
    page = context.new_page()
    requests, errors = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    selected_task = task or "<OCR_WITH_REGION>"
    text = "IMAGE_OCR_TEXT" if operation == "ocr" else "IMAGE_DESCRIPTION_TEXT"
    image = {"operation": operation, "task": selected_task,
             "image_base64": base64.b64encode(PNG).decode(), "image_mime_type": "image/png",
             "width": 1, "height": 1, "description": text if operation == "describe" else None,
             "text": text if operation == "ocr" else None,
             "lines": [{"text": text, "quad_box": [0, 0, 1, 0, 1, 1, 0, 1], "bbox": [0, 0, 1, 1]}] if operation == "ocr" else [],
             "model": {"model_id": "browser-fixture", "revision": "fixture", "device": "cpu", "dtype": "float32"}, "duration_ms": 1}

    def intercept(route):
        request = route.request
        if request.resource_type not in ("fetch", "xhr"):
            return route.continue_()
        if request.method == "OPTIONS":
            return route.fulfill(status=204, headers=CORS)
        path = urlparse(request.url).path.removeprefix("/api")
        value = None
        if path == "/auth/me":
            value = USER
        elif path == "/projects":
            value = {"projects": [PROJECT]}
        elif path == "/datalakes":
            value = {"connections": []}
        elif path == "/images/capabilities":
            value = {"enabled": True, "dependencies_installed": True, "model_downloaded": True,
                     "caption_tasks": TASKS, "default_caption_task": "<DETAILED_CAPTION>", "max_image_size_mb": 1}
        elif path in ("/images/describe/upload", "/images/ocr/upload"):
            assert path == f"/images/{operation}/upload"
            assert request.headers.get("authorization") == "Bearer synthetic-image-token"
            message = BytesParser(policy=default).parsebytes(
                b"Content-Type: " + request.headers["content-type"].encode() + b"\r\n\r\n" + request.post_data_buffer)
            parts = {part.get_param("name", header="content-disposition"): part.get_payload(decode=True) for part in message.iter_parts()}
            assert parts["file"] == PNG and parts["project_id"] == PROJECT["id"].encode()
            assert set(parts) == ({"file", "project_id", "task"} if operation == "describe" else {"file", "project_id"})
            if task:
                assert parts["task"].decode() == task
            requests.append(path)
            if timeout:
                return route.fulfill(status=504, json={"detail": {"job_id": JOB, "message": "Continue polling"}}, headers=CORS)
            value = {"job_id": JOB, "status": "completed", "project": PROJECT}
        elif path == f"/jobs/{JOB}":
            value = {"job_id": JOB, "type": "main", "status": "completed", "progress": 100,
                     "name": "image.png", "tags": [], "created_at": "2026-10-06T00:00:00", "project": PROJECT}
        elif path == f"/jobs/{JOB}/pages":
            value = {"job_id": JOB, "total_pages": 0, "pages_completed": 0, "pages_failed": 0, "pages": []}
        elif path == f"/jobs/{JOB}/result":
            value = {"job_id": JOB, "status": "completed", "type": "main", "completed_at": "2026-10-06T00:00:00",
                     "result": {"markdown": text, "metadata": {"format": "png", "size_bytes": len(PNG)}, "image": image}}
        if value is None:
            return route.fulfill(status=404, json={"detail": "Unavailable in fixture"}, headers=CORS)
        route.fulfill(json=value, headers=CORS)

    page.route("**/*", intercept)
    try:
        page.goto(url.rstrip("/") + "/convert?project_id=" + PROJECT["id"])
        upload = page.locator('input[type="file"]')
        assert ".png" in upload.get_attribute("accept")
        upload.set_input_files({"name": "image.png", "mimeType": "image/png", "buffer": PNG})
        expect(page.get_by_label("Processamento da imagem")).to_be_visible()
        page.get_by_label("Processamento da imagem").select_option(operation)
        expect(page.get_by_text("Destino dos resultados", exact=True)).to_have_count(0)
        expect(page.get_by_label("Custom Name (Optional)")).to_have_count(0)
        if operation == "describe":
            level = page.get_by_label("Detalhamento da descrição")
            expect(level).to_have_value("<DETAILED_CAPTION>")
            assert level.locator("option").count() == 3
            level.select_option(task)
        else:
            expect(page.get_by_label("Detalhamento da descrição")).to_have_count(0)
        submit = page.get_by_role("button", name="Processar arquivo", exact=True)
        if task == "<CAPTION>":
            # Exercise the server's configured limit, rather than a fixed 10MB.
            page.get_by_role("button", name="Remove file").click()
            page.locator('input[type="file"]').set_input_files({"name": "large.png", "mimeType": "image/png", "buffer": b"x" * (2 * 1024 * 1024)})
            expect(page.get_by_text("A imagem excede o limite de tamanho.")).to_be_visible()
            expect(submit).to_be_disabled()
            assert not requests
            page.get_by_role("button", name="Remove file").click()
            page.locator('input[type="file"]').set_input_files({"name": "image.png", "mimeType": "image/png", "buffer": PNG})
        expect(submit).to_be_enabled()
        submit.click()
        page.wait_for_url("**/jobs/" + JOB, timeout=15000)
        title = "Texto da imagem (OCR)" if operation == "ocr" else "Descrição da imagem"
        expect(page.get_by_role("heading", name=title, exact=True, level=2)).to_be_visible()
        expect(page.get_by_alt_text("Imagem enviada")).to_be_visible()
        expect(page.get_by_role("button", name="Copiar texto")).to_be_visible()
        assert len(requests) == 1
        if operation == "ocr":
            expect(page.locator("svg polygon")).to_have_count(1)
            page.get_by_role("button", name="Ocultar regiões").click()
            expect(page.locator("svg polygon")).to_have_count(0)
        page.reload()
        expect(page.get_by_role("heading", name=title, exact=True, level=2)).to_be_visible()
        expect(page.get_by_alt_text("Imagem enviada")).to_be_visible()
        if operation == "ocr":
            expect(page.locator("svg polygon")).to_have_count(1)
        assert not errors, errors
        print(f"PASS: {operation}, {selected_task}, timeout={timeout}, upload and configured job after F5")
    finally:
        context.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:3001")
    parser.add_argument("--chromium")
    args = parser.parse_args()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=args.chromium, headless=True, args=["--no-sandbox"])
        try:
            for task in TASKS:
                check(browser, args.url, "describe", task)
            check(browser, args.url, "ocr")
            check(browser, args.url, "ocr", timeout=True)
        finally:
            browser.close()
