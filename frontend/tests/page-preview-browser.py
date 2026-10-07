#!/usr/bin/env python3
"""Check PDF preview while conversion runs, live page updates and F5 recovery.

python frontend/tests/page-preview-browser.py --url http://localhost:3001
Uses synthetic API data and a local PDF.js worker; no uploaded user data.
"""
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, expect

JOB = "22222222-2222-4222-8222-222222222222"
USER = {"id": "preview-test", "username": "preview-test", "email": "preview@example.test",
        "is_active": True, "is_admin": False, "created_at": "2026-10-06T00:00:00"}
CORS = {"access-control-allow-origin": "*", "access-control-allow-headers": "*"}


def sample_pdf():
    stream = b"BT /F1 18 Tf 20 160 Td (Preview during conversion) Tj ET"
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
               b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
               b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"]
    pdf = b"%PDF-1.4\n"
    offsets = []
    for n, body in enumerate(objects, 1):
        offsets.append(len(pdf))
        pdf += f"{n} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(pdf)
    pdf += b"xref\n0 6\n0000000000 65535 f \n"
    pdf += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    return pdf + f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()


def check(browser, url):
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    auth = json.dumps({"state": {"user": USER, "token": "synthetic-preview-token"}, "version": 0})
    context.add_init_script("localStorage.setItem('auth-storage', " + json.dumps(auth) + ");")
    page = context.new_page()
    state = {"completed": False, "pdf_requests": [], "result_requests": [], "preview_auth": []}
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))

    def intercept(route):
        path = urlparse(route.request.url).path.removeprefix("/api")
        if "cdnjs.cloudflare.com" in route.request.url:
            worker = Path(__file__).resolve().parents[1] / "node_modules/pdfjs-dist/build/pdf.worker.min.js"
            return route.fulfill(path=str(worker), content_type="application/javascript", headers=CORS)
        if path == "/synthetic-page.pdf":
            state["preview_auth"].append(route.request.headers.get("authorization"))
            return route.fulfill(body=sample_pdf(), content_type="application/pdf", headers=CORS)
        if route.request.method == "OPTIONS":
            return route.fulfill(status=204, headers=CORS)
        if route.request.resource_type not in ("fetch", "xhr"):
            return route.continue_()
        pages = [{"page_number": n, "job_id": None if n == 1 else f"page-job-{n}",
                  "status": "completed" if state["completed"] or n == 1 else "processing",
                  "url": f"/jobs/{JOB}/pages/{n}/result", "error_message": None, "retry_count": 0}
                 for n in range(1, 6)]
        value = None
        if path == "/auth/me":
            value = USER
        elif path == f"/jobs/{JOB}":
            value = {"job_id": JOB, "type": "main", "status": "completed" if state["completed"] else "processing",
                     "progress": 100 if state["completed"] else 40, "name": "Preview check.pdf", "tags": [],
                     "total_pages": 5, "pages": pages, "created_at": "2026-10-06T00:00:00"}
        elif path == f"/jobs/{JOB}/pages":
            # The status's list must remain visible if a separate list is empty.
            value = {"job_id": JOB, "pages": [] if state["completed"] else pages, "total_pages": 5}
        elif path.endswith("/pdf") and path.startswith(f"/jobs/{JOB}/pages/"):
            state["pdf_requests"].append(path)
            value = {"url": "http://192.0.2.1/private-storage.pdf",
                     "preview_url": url.rstrip("/") + "/synthetic-page.pdf", "expires_in": 900,
                     # An expired storage signature must not block the API preview.
                     "expires_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()}
        elif path.endswith("/result") and path.startswith(f"/jobs/{JOB}"):
            state["result_requests"].append(path)
            value = {"job_id": JOB, "status": "completed", "result": {
                "markdown": "PAGE_MARKDOWN_CHECK", "metadata": {"format": "pdf", "size_bytes": 100}}}
        if value is None:
            return route.fulfill(status=404, json={"detail": "Synthetic fixture: unavailable"}, headers=CORS)
        route.fulfill(json=value, headers=CORS)

    page.route("**/*", intercept)
    try:
        page.goto(url.rstrip("/") + "/jobs/" + JOB)
        expect(page.get_by_text("Pages (5)", exact=True)).to_be_visible(timeout=20000)
        page.get_by_role("button", name="Page 2", exact=True).click()
        expect(page.locator("canvas")).to_be_visible(timeout=20000)
        assert state["pdf_requests"] == [f"/jobs/{JOB}/pages/2/pdf"]
        assert state["preview_auth"] == ["Bearer synthetic-preview-token"]
        page.get_by_role("tab", name="Markdown", exact=True).click()
        expect(page.get_by_text("Page conversion is processing.", exact=False)).to_be_visible()
        assert f"/jobs/{JOB}/pages/2/result" not in state["result_requests"]
        state["completed"] = True
        expect(page.get_by_text("PAGE_MARKDOWN_CHECK", exact=True)).to_be_visible(timeout=12000)
        expect(page.get_by_role("heading", name="Page 2", exact=True)).to_be_visible()
        page.reload()
        expect(page.get_by_text("Pages (5)", exact=True)).to_be_visible(timeout=15000)
        # Persisted pages without a child job id use the page-number route.
        page.get_by_role("button", name="Page 1", exact=True).click()
        page.get_by_role("tab", name="Markdown", exact=True).click()
        expect(page.get_by_text("PAGE_MARKDOWN_CHECK", exact=True)).to_be_visible()
        assert f"/jobs/{JOB}/pages/1/result" in state["result_requests"]
        assert not errors, errors
        print("PASS: processing PDF, polled Markdown, reload menu, result without child id")
    finally:
        context.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:3001")
    parser.add_argument("--chromium", default=None)
    args = parser.parse_args()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=args.chromium, headless=True, args=["--no-sandbox"])
        try:
            check(browser, args.url)
        finally:
            browser.close()
