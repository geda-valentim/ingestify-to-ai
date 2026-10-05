#!/usr/bin/env python3
"""Opt-in Chromium checks against a running frontend, with synthetic REST/WS.

No production API is contacted. Uses real getUserMedia + AudioWorklet, a fake
microphone and Playwright's WebSocketRoute (Playwright >=1.48).
  python frontend/tests/live-browser.py --url http://127.0.0.1:3013
"""
import argparse
import json
import re
import struct
import time
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, expect

USER = {"id": "browser-test-user", "username": "browser-test", "email": "browser@example.test",
        "is_active": True, "is_admin": False, "created_at": "2026-10-05T00:00:00"}
PROJECT = {"id": "11111111-1111-4111-8111-111111111111", "name": "Projeto teste",
           "description": None, "archived": False, "job_count": 0, "root_job_count": 0,
           "failed_count": 0, "active_count": 0, "last_job_at": None, "api_keys": [], "folders": []}
JOB = "22222222-2222-4222-8222-222222222222"
OLD_JOB = "33333333-3333-4333-8333-333333333333"
CORS = {"access-control-allow-origin": "*", "access-control-allow-headers": "*",
        "access-control-allow-methods": "GET,POST,DELETE,OPTIONS"}


def wait_condition(page, predicate):
    deadline = time.monotonic() + 10
    while not predicate():
        assert time.monotonic() < deadline, "Synthetic request did not arrive"
        page.wait_for_timeout(20)


def scenario(browser, url, mode):
    context = browser.new_context(permissions=["microphone"], locale="pt-BR")
    context.add_init_script("""(() => {
      localStorage.setItem('auth-storage', JSON.stringify({state: {user: USER,
        token: 'synthetic-browser-test-token'}, version: 0}));
      const original = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
      window.__testStreams = [];
      navigator.mediaDevices.getUserMedia = async (...args) => {
        const stream = await original(...args); window.__testStreams.push(stream); return stream;
      };
    })()""".replace("USER", json.dumps(USER)))
    page = context.new_page()
    errors, packets, controls, creations, cancellations = [], [], [], [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    state = {"samples": 0, "event": 0}

    def rest(route):
        path, method = urlparse(route.request.url).path, route.request.method
        if method == "OPTIONS":
            route.fulfill(status=204, headers=CORS)
        elif path == "/auth/me":
            route.fulfill(json=USER, headers=CORS)
        elif path == "/projects":
            route.fulfill(json={"projects": [PROJECT], "limits": {"max_projects": 1000,
                            "max_folders_per_project": 1000}}, headers=CORS)
        elif path == "/projects/resolve":
            route.fulfill(json={"valid": True, "match": {"id": PROJECT["id"], "name": PROJECT["name"]}}, headers=CORS)
        elif path == "/transcribe/live/sessions" and method == "POST":
            creations.append(route.request.post_data_json)
            if mode == "late-admission" and len(creations) == 1:
                state["pending_admission"] = route
                return
            route.fulfill(status=201, json={"job_id": JOB, "ws_url": f"ws://live.test/{JOB}",
                "ticket": "synthetic-test-ticket", "max_duration_seconds": 1800}, headers=CORS)
        elif path in [f"/transcribe/live/sessions/{JOB}", f"/transcribe/live/sessions/{OLD_JOB}"] and method == "DELETE":
            cancellations.append(path)
            route.fulfill(json={"job_id": JOB, "state": "cancelled"}, headers=CORS)
        else:
            route.fulfill(status=404, json={"detail": "Unexpected synthetic request"}, headers=CORS)

    page.route("http://localhost:8080/**", rest)
    page.route("http://127.0.0.1:8080/**", rest)
    if mode == "denied":
        page.add_init_script("navigator.mediaDevices.getUserMedia = () => Promise.reject(new DOMException('Permission denied', 'NotAllowedError'))")
    if mode == "flush-timeout":
        page.add_init_script("""const NativeWorklet = window.AudioWorkletNode;
          window.AudioWorkletNode = class extends NativeWorklet { constructor(...args) {
            super(...args); const original = this.port.postMessage.bind(this.port);
            this.port.postMessage = (data, ...rest) => { if (data !== 'finish') original(data, ...rest); };
          }};""")

    def socket(ws):
        def event(kind, **fields):
            state["event"] += 1
            ws.send(json.dumps({"type": kind, "event_seq": state["event"], "job_id": JOB, **fields}))
        state["send_event"] = event
        state["socket"] = ws

        def message(data):
            if isinstance(data, str):
                control = json.loads(data)
                controls.append(control)
                if control["type"] == "authenticate":
                    assert control["protocol"] == 1 and "ticket" in control
                    event("session.ready", backend="whisper", model="turbo")
                elif control["type"] == "finish":
                    assert control["last_seq"] == len(packets) - 1
                    event("session.completed", result_url=f"/jobs/{JOB}/result")
                return
            seq, offset = struct.unpack_from("<IQ", data)
            assert seq == len(packets) and offset == state["samples"]
            assert 14 <= len(data) <= 6412 and (len(data) - 12) % 2 == 0
            state["samples"] += (len(data) - 12) // 2
            packets.append(data)
            if len(packets) == 1:
                event("transcript.partial", utterance_id=0, revision=1, text="Hipótese antiga")
            elif len(packets) == 2:
                event("transcript.partial", utterance_id=0, revision=2, text="Hipótese revisada")
        ws.on_message(message)

    page.route_web_socket("ws://live.test/**", socket)
    assert page.goto(url.rstrip("/") + "/live", wait_until="networkidle").status == 200
    expect(page.get_by_role("heading", name="Transcrever ao vivo")).to_be_visible()
    page.get_by_role("combobox").first.click()
    page.get_by_role("option", name=re.compile("Projeto teste")).click()
    page.get_by_role("button", name="Iniciar microfone", exact=True).click()
    status = page.locator("main [role=status]")
    if mode == "late-admission":
        page.wait_for_function("window.__testStreams.length === 1")
        # Wait until the POST was sent; keeping its route pending simulates a
        # slow admission response without a timing-dependent sleep.
        wait_condition(page, lambda: "pending_admission" in state)
        page.get_by_role("button", name="Cancelar", exact=True).click()
        expect(status).to_contain_text("Sessão cancelada")
        page.get_by_role("button", name="Iniciar microfone", exact=True).click()
    if mode == "denied":
        expect(status).to_contain_text("Sessão interrompida")
        expect(page.locator("main [role=alert]")).to_contain_text("Permission denied")
        assert not creations and not packets
    else:
        expect(status).to_contain_text("Ouvindo")
        if mode == "late-admission":
            state["pending_admission"].fulfill(status=201, json={"job_id": OLD_JOB,
                "ws_url": f"ws://live.test/{OLD_JOB}", "ticket": "synthetic-old-ticket",
                "max_duration_seconds": 1800}, headers=CORS)
            page.wait_for_function("window.__testStreams.length === 2 && window.__testStreams[0].getTracks().every(t => t.readyState === 'ended')")
            wait_condition(page, lambda: f"/transcribe/live/sessions/{OLD_JOB}" in cancellations)
            expect(status).to_contain_text("Ouvindo")
            assert page.evaluate("window.__testStreams[1].getAudioTracks()[0].readyState") == "live"
        expect(page.get_by_test_id("live-partial")).to_have_text("Hipótese revisada")
        assert "Hipótese antiga" not in page.locator("main").inner_text()
        state["send_event"]("transcript.final", segment_id=0, utterance_id=0, start=0, end=.5, text="Frase confirmada.")
        expect(page.get_by_text("Frase confirmada.", exact=True)).to_have_count(1)
        if mode in ["success", "late-admission"]:
            page.get_by_role("button", name="Finalizar", exact=True).click()
            expect(status).to_contain_text("Transcrição salva")
            expect(page.get_by_role("link", name="Ver resultado e baixar legendas")).to_have_attribute("href", f"/jobs/{JOB}")
            assert any(c["type"] == "finish" for c in controls)
        elif mode == "cancel":
            page.get_by_role("button", name="Cancelar", exact=True).click()
            expect(status).to_contain_text("Sessão cancelada")
            page.wait_for_function("window.__testStreams.every(s => s.getTracks().every(t => t.readyState === 'ended'))")
            assert cancellations and any(c["type"] == "cancel" for c in controls)
        elif mode == "interrupted":
            state["socket"].close(code=1011, reason="Synthetic interruption")
            expect(status).to_contain_text("Sessão interrompida")
            expect(page.locator("main [role=alert]")).to_be_visible()
            assert len(creations) == 1
        elif mode == "flush-timeout":
            page.get_by_role("button", name="Finalizar", exact=True).click()
            expect(status).to_contain_text("Sessão interrompida")
            expect(page.locator("main [role=alert]")).to_contain_text("não conseguiu finalizar")
            assert not any(c["type"] == "finish" for c in controls)
        page.wait_for_function("window.__testStreams.every(s => s.getTracks().every(t => t.readyState === 'ended'))")
        assert creations[0]["project_id"] == PROJECT["id"]
        assert state["samples"] > 0
    assert not errors, errors
    print(f"PASS browser {mode}: frames={len(packets)}, samples={state['samples']}")
    context.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:3013")
    parser.add_argument("--chromium")
    modes = ["success", "cancel", "denied", "interrupted", "late-admission", "flush-timeout"]
    parser.add_argument("--scenario", choices=modes + ["all"], default="all")
    args = parser.parse_args()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=args.chromium, headless=True, args=[
            "--no-sandbox", "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"])
        for mode in (modes if args.scenario == "all" else [args.scenario]):
            scenario(browser, args.url, mode)
        browser.close()
