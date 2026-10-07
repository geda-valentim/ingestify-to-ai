#!/usr/bin/env python3
"""Chromium checks of file transcription previews, with synthetic API responses.

No audio is uploaded and no provider is called. Requires Playwright.
  python frontend/tests/transcript-progress-browser.py --url http://localhost:3001
"""
import argparse
import json
import time
from urllib.parse import urlparse, parse_qs

from playwright.sync_api import sync_playwright, expect

JOB = "22222222-2222-4222-8222-222222222222"
USER = {"id": "preview-test", "username": "preview-test", "email": "preview@example.test",
        "is_active": True, "is_admin": False, "created_at": "2026-10-06T00:00:00"}
CORS = {"access-control-allow-origin": "*", "access-control-allow-headers": "*"}


def check(browser, url, slow=False):
    context = browser.new_context()
    auth = json.dumps({"state": {"user": USER, "token": "synthetic-preview-token"}, "version": 0})
    context.add_init_script("localStorage.setItem('auth-storage', " + json.dumps(auth) + ");")
    page = context.new_page()
    state = {"status": "processing", "segments": [], "requests": [], "held": [], "hold": False}
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    def rest(route):
        parsed = urlparse(route.request.url)
        path = parsed.path.removeprefix("/api")
        def respond(value, status=200):
            route.fulfill(status=status, json=value, headers=CORS)
        if route.request.method == "OPTIONS":
            route.fulfill(status=204, headers=CORS)
        elif path == "/auth/me":
            respond(USER)
        elif path == f"/jobs/{JOB}":
            respond({"job_id": JOB, "status": state["status"], "job_type": "main",
                     "progress": 50, "name": "Preview check", "filename": "preview.wav",
                     "source_type": "audio", "media_duration": 30, "transcribed_seconds": 10,
                     "tags": [], "pages": [], "created_at": "2026-10-06T00:00:00"})
        elif path == f"/jobs/{JOB}/transcript/partial":
            since = int(parse_qs(parsed.query).get("since", ["0"])[0])
            state["requests"].append(since)
            value = {"job_id": JOB, "status": state["status"], "segments": state["segments"][since:],
                     "next": len(state["segments"])}
            if state["hold"]:
                state["held"].append((route, value))
            else:
                respond(value)
        elif path == f"/jobs/{JOB}/pages":
            respond({"job_id": JOB, "pages": [], "total_pages": 0})
        elif path == f"/jobs/{JOB}/result":
            respond({"job_id": JOB, "status": "completed", "result": {
                "markdown": "FINAL_RESULT_CHECK", "metadata": {"format": "audio", "size_bytes": 100}}})
        else:
            respond({"detail": "Synthetic fixture: unavailable"}, 404)

    def intercept(route):
        parsed = urlparse(route.request.url)
        if parsed.path.startswith(("/api/", "/auth/", "/projects", "/tags")) or (
            parsed.path.startswith("/jobs/") and route.request.resource_type in ("fetch", "xhr")
        ):
            rest(route)
        else:
            route.continue_()

    page.route("**/*", intercept)
    try:
        state["segments"] = [{"start": 0, "end": 4, "text": "FIRST_SEGMENT_CHECK"}]
        page.goto(url.rstrip("/") + "/jobs/" + JOB)
        expect(page.get_by_text("FIRST_SEGMENT_CHECK", exact=True)).to_be_visible(timeout=20000)
        if slow:
            # Start after mounting; development StrictMode intentionally replays effects.
            state["hold"] = True
            state["segments"].append({"start": 4, "end": 8, "text": "SECOND_SEGMENT_CHECK"})
            deadline = time.monotonic() + 20
            while not state["held"]:
                assert time.monotonic() < deadline, "Preview request missing"
                page.wait_for_timeout(50)
            page.wait_for_timeout(6500)
            assert len(state["held"]) == 1, "Slow network caused overlapping requests with the same cursor"
            for route, value in state["held"]:
                route.fulfill(json=value, headers=CORS)
            state["held"].clear()
            expect(page.get_by_text("SECOND_SEGMENT_CHECK", exact=True)).to_have_count(1)
            expect(page.get_by_text("FIRST_SEGMENT_CHECK", exact=True)).to_have_count(1)
        else:
            expect(page.get_by_text("FIRST_SEGMENT_CHECK", exact=True)).to_be_visible(timeout=20000)
            state["segments"].append({"start": 4, "end": 8, "text": "SECOND_SEGMENT_CHECK"})
            expect(page.get_by_text("SECOND_SEGMENT_CHECK", exact=True)).to_be_visible(timeout=10000)
            expect(page.get_by_text("FIRST_SEGMENT_CHECK", exact=True)).to_have_count(1)
            assert 1 in state["requests"], "Preview did not advance its cursor"
            state["segments"] = []
            expect(page.get_by_text("FIRST_SEGMENT_CHECK", exact=True)).to_have_count(0, timeout=10000)
            state["segments"] = [{"start": 0, "end": 5, "text": "RETRY_SEGMENT_CHECK"}]
            expect(page.get_by_text("RETRY_SEGMENT_CHECK", exact=True)).to_be_visible(timeout=10000)
            state["status"] = "completed"
            expect(page.get_by_text("FINAL_RESULT_CHECK", exact=True)).to_be_visible(timeout=10000)
            expect(page.get_by_text("RETRY_SEGMENT_CHECK", exact=True)).to_have_count(0)
        assert not errors, errors
    finally:
        for route, _ in state["held"]:
            route.abort()
        context.close()


def check_result_recovery(browser, url, mobile=False):
    context = browser.new_context(viewport={"width": 390 if mobile else 1440, "height": 844})
    auth = json.dumps({"state": {"user": USER, "token": "synthetic-preview-token"}, "version": 0})
    context.add_init_script("localStorage.setItem('auth-storage', " + json.dumps(auth) + ");")
    page = context.new_page()
    state = {"available": False}

    def intercept(route):
        path = urlparse(route.request.url).path.removeprefix("/api")
        if route.request.method == "OPTIONS":
            return route.fulfill(status=204, headers=CORS)
        if route.request.resource_type not in ("fetch", "xhr"):
            return route.continue_()
        if path == f"/jobs/{JOB}":
            route.fulfill(json={"job_id": JOB, "type": "main", "status": "completed", "progress": 100,
                                "created_at": "2026-10-06T00:00:00", "tags": []}, headers=CORS)
        elif path == f"/jobs/{JOB}/result":
            if state["available"]:
                route.fulfill(json={"job_id": JOB, "type": "main", "status": "completed", "result": {
                    "markdown": "RECOVERED_RESULT_CHECK", "metadata": {"format": "mp3", "size_bytes": 100}}}, headers=CORS)
            else:
                route.fulfill(status=404, json={"detail": "Result unavailable"}, headers=CORS)
        elif path == "/auth/me":
            route.fulfill(json=USER, headers=CORS)
        else:
            route.fulfill(status=404, json={"detail": "Synthetic fixture: unavailable"}, headers=CORS)

    page.route("**/*", intercept)
    try:
        page.goto(url.rstrip("/") + "/jobs/" + JOB)
        expect(page.get_by_text("Could not load the result", exact=True)).to_be_visible(timeout=30000)
        state["available"] = True
        page.get_by_role("button", name="Try again", exact=True).click()
        expect(page.get_by_text("RECOVERED_RESULT_CHECK", exact=True)).to_be_visible(timeout=15000)
        expect(page.get_by_text("Could not load the result", exact=True)).to_have_count(0)
    finally:
        context.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:3001")
    parser.add_argument("--chromium", default=None)
    args = parser.parse_args()
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=args.chromium, headless=True, args=["--no-sandbox"])
        for slow in (False, True):
            check(browser, args.url, slow)
            print("PASS", "slow network" if slow else "incremental text, retry, final result", flush=True)
        for mobile in (False, True):
            check_result_recovery(browser, args.url, mobile)
            print("PASS", "result error and recovery", "mobile" if mobile else "desktop", flush=True)
        browser.close()
