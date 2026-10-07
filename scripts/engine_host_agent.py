#!/usr/bin/env python3
"""Restricted host executor. Root-owned registration, no SQL/cloud credentials."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
import urllib.parse

SERVICES = {
    "worker",
    "worker-audio",
    "worker-vision",
    "worker-live",
    "worker-dispatch",
    "worker-remote",
}
ACTIONS = {
    "test",
    "start",
    "drain_stop",
    "restart",
    "scale",
    "warmup",
    "cooldown",
    "apply_profile",
}


# What the operator should do for refusals that stop the agent (journalctl only).
FAILURE_HINTS = {
    "REGISTERED_MANIFEST_CHANGED": "compose files changed since registration; re-register the host "
    "(docs/runbooks/engine-control-bootstrap.md, 'Re-registrar o host')",
    "HOST_IDENTITY_REQUIRED": "the API does not know this host's token; check that "
    "secrets/engine_host_identities.json is readable by the API container and re-register if needed",
    "Registered images must be pinned by digest": "re-register after building the worker images",
}


def describe_failure(exc, secret=None):
    """One log line for a failed cycle: type, code/message and a hint. Never the token."""
    kind = type(exc).__name__
    if isinstance(exc, urllib.error.HTTPError):
        code = None
        try:
            body = json.loads(exc.read().decode("utf-8", "replace") or "null")
            detail = body.get("detail") if isinstance(body, dict) else None
            code = detail.get("code") if isinstance(detail, dict) else detail
        except Exception:
            pass
        text = f"HTTP {exc.code}" + (f" {code}" if code else "")
    elif isinstance(exc, urllib.error.URLError):
        text = f"API unreachable ({exc.reason})"
    else:
        text = str(exc)
    if secret:
        text = text.replace(secret, "***")
    text = " ".join(text.split())[:300]
    hint = next((h for key, h in FAILURE_HINTS.items() if text.startswith(key) or f" {key}" in text), None)
    return f"{kind}: {text}" + (f" — {hint}" if hint else "")


class HostAgent:
    def __init__(self, path):
        path = Path(path)
        if path.stat().st_mode & 0o077:
            raise ValueError("Registration must have permissions 0600")
        self.config = json.loads(path.read_text())
        c = self.config
        if not set(c["services"]).issubset(SERVICES) or not c["services"]:
            raise ValueError("Unknown service")
        parsed = urllib.parse.urlsplit(c["api_url"])
        if parsed.scheme != "https" and not (
            parsed.scheme == "http"
            and parsed.hostname in ("127.0.0.1", "localhost", "::1")
        ):
            raise ValueError(
                "Use verified HTTPS or host loopback for the machine identity"
            )
        if not c["project"].replace("-", "").replace("_", "").isalnum():
            raise ValueError("Invalid Compose project")
        self.done_path = Path(
            c.get("state_path", "/var/lib/ingestify-engine-agent/state.json")
        )
        self.done_path.parent.mkdir(parents=True, exist_ok=True)
        self.done = (
            json.loads(self.done_path.read_text()) if self.done_path.exists() else {}
        )
        self.active = None
        self.heartbeat_stop = threading.Event()
        self.heartbeat_lost = False

    def request(self, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            self.config["api_url"].rstrip("/")
            + "/internal/engine-hosts/"
            + self.config["host_id"]
            + path,
            data=data,
            headers={
                "Content-Type": "application/json",
                "X-Engine-Host-Token": self.config["machine_token"],
            },
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.load(response)

    def verify_registration(self):
        c = self.config
        hasher = hashlib.sha256()
        for filename, expected in c["manifests"].items():
            path = Path(filename)
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != expected:
                raise ValueError("REGISTERED_MANIFEST_CHANGED")
            hasher.update(str(path.resolve()).encode() + actual.encode())
        for service, entry in c["services"].items():
            if (
                not entry["image"].startswith("sha256:")
                and "@sha256:" not in entry["image"]
            ):
                raise ValueError("Registered images must be pinned by digest")
        return hasher.hexdigest()

    def inventory(self):
        c = self.config
        return {
            "services": list(c["services"]),
            "manifest_hash": self.verify_registration(),
            "gpu_uuids": c.get("gpu_uuids", []),
            "project": c["project"],
            "images": {s: e["image"] for s, e in c["services"].items()},
        }

    def check(self):
        if self.active:
            if self.heartbeat_lost:
                raise RuntimeError("HOST_AUTHORITY_UNAVAILABLE")
            reply = self.request(
                f'/operations/{self.active["operation_id"]}/check?generation={self.active["generation"]}'
            )
            if reply["cancel_requested"]:
                raise RuntimeError("CANCELLED")

    def event(self, stage, message, effect=False):
        self.check()
        self.request(
            f'/operations/{self.active["operation_id"]}/events',
            {
                "generation": self.active["generation"],
                "stage": stage,
                "message": message,
                "effect": effect,
            },
        )

    def compose(self, overlay):
        c = self.config
        cmd = ["docker", "compose", "--project-name", c["project"]]
        for filename in c["manifests"]:
            cmd.extend(["-f", filename])
        cmd.extend(["-f", overlay])
        return cmd

    def run(self, argv, timeout=180):
        self.check()
        # Do not return raw container logs/env/Compose config to the browser.
        child = subprocess.Popen(
            argv,
            cwd=self.config["cwd"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        deadline = time.monotonic() + timeout
        try:
            while True:
                self.check()
                try:
                    output, _ = child.communicate(
                        timeout=min(1, max(0.01, deadline - time.monotonic()))
                    )
                    break
                except subprocess.TimeoutExpired:
                    if time.monotonic() >= deadline:
                        raise RuntimeError("HOST_COMMAND_TIMEOUT")
        except BaseException:
            child.terminate()
            try:
                child.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.communicate()
            raise
        if child.returncode:
            raise RuntimeError(f"HOST_COMMAND_FAILED:{child.returncode}")
        return output

    def inspect(self, service, overlay):
        ids = self.run(
            self.compose(overlay) + ["ps", "--all", "--quiet", service]
        ).split()
        if not ids:
            return []
        rows = json.loads(self.run(["docker", "inspect", *ids]))
        return [
            {"id": r["Id"], "state": r["State"]["Status"], "image": r["Image"]}
            for r in rows
        ]

    def apply(self, item):
        self.active = item
        p = item["plan"]
        profile = p["profile"]
        service = p["service"]
        action = p["type"]
        if action not in ACTIONS or service not in self.config["services"]:
            raise ValueError("ACTION_OR_TARGET_NOT_REGISTERED")
        inventory = self.inventory()
        if p["manifest_hash"] != inventory["manifest_hash"]:
            raise ValueError("MANIFEST_STALE")
        if profile.get("gpu_uuid") and profile["gpu_uuid"] not in self.config.get(
            "gpu_uuids", []
        ):
            raise ValueError("GPU_NOT_REGISTERED")
        registration = self.config["services"][service]
        expected = "cuda" if profile.get("gpu_uuid") else "cpu"
        env = {
            "INGESTIFY_RUNTIME_REVISION": str(p["profile_revision"]),
            "INGESTIFY_MODEL_PROFILE": profile["model_profile_id"],
            "INGESTIFY_RUNTIME_FEATURE": p["feature"],
            "INGESTIFY_EXPECTED_DEVICE": expected,
            "ENGINE_CONTROL_ENABLED": "true",
            "DEVICE": expected,
        }
        if p["feature"] == "transcription":
            env.update(WHISPER_DEVICE=expected, WHISPER_MODEL=profile["model"]["model"])
        if p["feature"] == "live-transcription":
            env.update(WHISPER_DEVICE=expected, WHISPER_MODEL=profile["model"]["model"])
        override = {"image": registration["image"], "environment": env}
        if registration.get("command"):
            command = list(registration["command"])
            if service != "worker-live":
                if command[:4] != ["celery", "-A", "workers.celery_app", "worker"]:
                    raise ValueError("REGISTERED_COMMAND_NOT_SUPPORTED")
                command = [
                    arg for arg in command if not arg.startswith("--concurrency=")
                ]
                if "--concurrency" in command:
                    pos = command.index("--concurrency")
                    del command[pos : pos + 2]
                command.append(
                    f"--concurrency={profile['binding']['executions_per_worker']}"
                )
            override["command"] = command
        if profile["binding"].get("cpu"):
            override["cpus"] = profile["binding"]["cpu"]
        if profile.get("memory_mb"):
            override["mem_limit"] = f"{profile['memory_mb']}m"
        if profile.get("gpu_uuid"):
            override["deploy"] = {
                "resources": {
                    "reservations": {
                        "devices": [
                            {
                                "driver": "nvidia",
                                "device_ids": [profile["gpu_uuid"]],
                                "capabilities": ["gpu"],
                            }
                        ]
                    }
                }
            }
        # Artifacts persist across boot; the operator's base .env/manifests are untouched.
        overlay = (
            self.done_path.parent
            / f'{"observe-" if item.get("observe_only") else ""}{service}.json'
        )
        overlay.write_text(json.dumps({"services": {service: override}}))
        os.chmod(overlay, 0o600)
        replicas = (
            0 if action in ("cooldown", "drain_stop") else profile["desired_replicas"]
        )
        if action == "warmup":
            replicas = max(replicas, profile["min_ready_replicas"])
        override.setdefault("deploy", {})["replicas"] = replicas
        overlay.write_text(json.dumps({"services": {service: override}}))
        if action == "test":
            states = self.inspect(service, str(overlay))
            return {
                "replicas_alive": sum(r["state"] == "running" for r in states),
                "ready_replicas": 0,
                "verified_host": True,
            }
        observe_only = item.get("observe_only", False)
        if not observe_only:
            self.event("applying", f"Aplicando {replicas} réplicas de {service}", True)
        argv = self.compose(str(overlay))
        if action in ("restart", "warmup", "apply_profile"):
            argv += ["up", "-d", "--force-recreate"]
        else:
            argv += ["up", "-d"]
        argv += [
            "--no-deps",
            "--no-build",
            "--pull",
            "never",
            "--scale",
            f"{service}={replicas}",
            service,
        ]
        if not observe_only:
            self.run(argv)
        self.event("verifying", "Conferindo processos, imagem e modelo carregado")
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            self.check()
            states = self.inspect(service, str(overlay))
            alive = [r for r in states if r["state"] == "running"]
            if not replicas and not alive:
                return {
                    "replicas_alive": 0,
                    "ready_replicas": 0,
                    "cold": True,
                    "service": service,
                }
            ready = []
            if len(alive) == replicas:
                for row in alive:
                    if row["image"] != registration["image"] and registration[
                        "image"
                    ].startswith("sha256:"):
                        raise RuntimeError("IMAGE_MISMATCH")
                    if service == "worker-live":
                        result = json.loads(
                            self.run(
                                [
                                    "docker",
                                    "exec",
                                    row["id"],
                                    "python",
                                    "-c",
                                    "import urllib.request,json;print(urllib.request.urlopen('http://localhost:8091/health').read().decode())",
                                ]
                            )
                        )
                        if (
                            result.get("ready")
                            and result.get("runtime_revision")
                            == str(p["profile_revision"])
                            and result.get("model_profile_id")
                            == profile["model_profile_id"]
                            and result.get("model") == profile["model"]["model"]
                        ):
                            ready.append(row["id"])
                    else:
                        observations = json.loads(
                            self.run(
                                [
                                    "docker",
                                    "exec",
                                    row["id"],
                                    "python",
                                    "-m",
                                    "workers.engine_control.readiness",
                                ]
                            )
                        )
                        children = [
                            x
                            for x in observations
                            if x.get("ready")
                            and x.get("revision") == str(p["profile_revision"])
                            and x.get("profile") == profile["model_profile_id"]
                        ]
                        if len(children) == profile["binding"]["executions_per_worker"]:
                            ready.append(row["id"])
                if len(ready) == replicas:
                    return {
                        "replicas_alive": replicas,
                        "ready_replicas": len(ready),
                        "containers": ready,
                        "model_profile_id": profile["model_profile_id"],
                        "revision": p["profile_revision"],
                        "service": service,
                    }
            time.sleep(2)
        raise RuntimeError("MODEL_READINESS_TIMEOUT")

    def loop(self):
        while True:
            try:
                self.request("/heartbeat", {"inventory": self.inventory()})
                item = self.request("/next")
                if item:
                    key = item["operation_id"] + ":" + str(item["generation"])
                    # Crash after effect: never replay automatically; report uncertain to reconciler.
                    if key in self.done:
                        result = self.done[key]
                    else:
                        self.done[key] = {"ok": False, "code": "HOST_EFFECT_UNCERTAIN"}
                        self.done_path.write_text(json.dumps(self.done))
                        self.heartbeat_lost = False
                        self.heartbeat_stop.clear()

                        def maintain_authority():
                            while not self.heartbeat_stop.wait(5):
                                try:
                                    self.request(
                                        "/heartbeat", {"inventory": self.inventory()}
                                    )
                                except Exception:
                                    self.heartbeat_lost = True
                                    return

                        heartbeat = threading.Thread(
                            target=maintain_authority, daemon=True
                        )
                        heartbeat.start()
                        try:
                            observed = self.apply(item)
                            result = {"ok": True, "observed": observed}
                        except Exception as exc:
                            result = {"ok": False, "code": str(exc)[:200]}
                        finally:
                            self.heartbeat_stop.set()
                            heartbeat.join(timeout=11)
                        self.done[key] = result
                        self.done_path.write_text(json.dumps(self.done))
                    self.request(
                        f'/operations/{item["operation_id"]}/result',
                        dict(result, generation=item["generation"]),
                    )
                self.active = None
            except Exception as exc:
                line = describe_failure(exc, self.config.get("machine_token"))
                now = time.monotonic()
                # Log each new reason at once, and repeat it once a minute while it lasts.
                if line != getattr(self, "_last_failure", None) or now - getattr(self, "_last_failure_at", 0) >= 60:
                    print(f"Agent unavailable: {line}", flush=True)
                    self._last_failure, self._last_failure_at = line, now
            else:
                if getattr(self, "_last_failure", None):
                    print("Agent recovered", flush=True)
                    self._last_failure = None
            time.sleep(5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    with open(args.config + ".lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        HostAgent(args.config).loop()
