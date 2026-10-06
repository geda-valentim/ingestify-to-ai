"""Audit every resolved dependency; unknown/unpinned packages fail the gate."""
import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlsplit
from packaging.utils import canonicalize_name, parse_wheel_filename
from packaging.version import Version
from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[2]
NORMAL = [f"backend/requirements-{name}.txt" for name in
          ("cpu", "cuda", "vision", "vision-cuda", "live-cuda", "remote")]
LOCKS = ["backend/requirements-test.lock",
         ".github/requirements-security.lock",
         "backend/workers/engines/modal_apps/requirements-whisper-modal.lock"]
RESTRICTED = [f"backend/requirements-{name}.lock" for name in
              ("whisperx-cpu", "whisperx-cuda", "whisperx-worker-cpu",
               "whisperx-worker-cuda", "live-whisperx-cuda", "diart-cuda")]
RESTRICTED += ["backend/requirements-diart-cpu.lock.txt"]


def lock_pins(path):
    pins = {}
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if re.fullmatch(r"--hash=sha256:[0-9a-f]{64}\s*\\?", line):
            continue
        if re.fullmatch(r"--(?:extra-)?index-url(?:=|\s+)https://\S+", line):
            continue
        if line.startswith("-"):
            raise ValueError("Unsupported dependency directive in audit input")
        requirement = Requirement(line.removesuffix("\\").strip())
        name = requirement.name
        if requirement.url:
            url = requirement.url
            wheel_name, version, _, _ = parse_wheel_filename(
                unquote(urlsplit(url).path.rsplit("/", 1)[-1]))
            if canonicalize_name(wheel_name) != canonicalize_name(name):
                raise ValueError("Wheel package does not match requirement")
            version = version.public
        else:
            specs = list(requirement.specifier)
            if len(specs) != 1 or specs[0].operator != "==":
                raise ValueError("Unpinned or unsupported dependency in audit input")
            version = Version(specs[0].version).public
        key = canonicalize_name(name)
        if key in pins and pins[key] != version:
            raise ValueError("Conflicting package versions")
        pins[key] = version
    if not pins:
        raise ValueError("Empty dependency set")
    return [f"{name}=={version}" for name, version in sorted(pins.items())]


def audit(profile, resolve):
    with tempfile.TemporaryDirectory() as temp:
        source = ROOT / profile
        if resolve:
            source = Path(temp) / "resolved.txt"
            result = subprocess.run(["uv", "pip", "compile", str(ROOT / profile),
                "--python-version", "3.13", "--python-platform", "x86_64-unknown-linux-gnu",
                "--output-file", str(source)], capture_output=True)
            if result.returncode:
                raise RuntimeError("Dependency resolution failed")
        normalized = Path(temp) / "requirements.txt"
        pins = lock_pins(source)
        normalized.write_text("\n".join(pins) + "\n")
        report = Path(temp) / "audit.json"
        result = subprocess.run(["pip-audit", "--no-deps", "--disable-pip",
            "-r", str(normalized), "--format", "json", "--output", str(report)],
            capture_output=True)
        if result.returncode not in (0, 1) or not report.exists():
            raise RuntimeError("Advisory lookup failed")
        data = json.loads(report.read_text())
        deps = data["dependencies"]
        if len(deps) != len(pins) or any(d.get("skip_reason") for d in deps):
            raise RuntimeError("Incomplete advisory coverage")
        findings = [{"package": d["name"], "version": d["version"],
                     "advisories": [v["id"] for v in d.get("vulns", [])]}
                    for d in deps if d.get("vulns")]
        print(json.dumps({"profile": profile, "packages": len(deps), "findings": findings}))
        return result.returncode == 0 and not findings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", choices=("normal", "restricted", "all"), default="normal")
    args = parser.parse_args()
    profiles = []
    if args.scope in ("normal", "all"):
        profiles += [(p, True) for p in NORMAL] + [(p, False) for p in LOCKS]
    if args.scope in ("restricted", "all"):
        profiles += [(p, False) for p in RESTRICTED]
    passed = True
    for profile, resolve in profiles:
        try:
            passed = audit(profile, resolve) and passed
        except Exception as exc:
            # Never echo a raw requirement URL or resolver output containing credentials.
            print(json.dumps({"profile": profile, "error": type(exc).__name__, "passed": False}))
            passed = False
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
