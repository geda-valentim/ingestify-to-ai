"""Current checkout and new commits; historical containment is a separate check."""
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


def run_scan(args):
    with tempfile.TemporaryDirectory() as temp:
        report = Path(temp) / "redacted.json"
        result = subprocess.run(["gitleaks", *args, "--redact", "--no-banner",
            "--log-level", "error", "--report-format", "json", "--report-path", str(report)],
            capture_output=True)
        if report.exists():
            for item in json.loads(report.read_text()):
                print(json.dumps({k: item[k] for k in ("RuleID", "File", "StartLine", "Fingerprint")}))
        if result.returncode not in (0, 1):
            print("Secret scanner failed; refusing incomplete scan")
        return result.returncode == 0


def revision(value):
    if not re.fullmatch(r"[0-9a-f]{40}", value or ""):
        raise ValueError("Invalid event revision")
    return value


def scan_checkout():
    root = Path.cwd()
    names = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"])
    with tempfile.TemporaryDirectory() as temp:
        target = Path(temp)
        for raw in names.split(b"\0"):
            if not raw:
                continue
            relative = Path(os.fsdecode(raw))
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Invalid checkout path")
            source = root / relative
            destination = target / relative
            if source.is_symlink():
                # Scan the tracked symlink text, never content outside the checkout.
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(os.readlink(source))
            elif source.is_file():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
        original = Path.cwd()
        try:
            os.chdir(target)
            return run_scan(["dir", ".", "--config", str(root / ".gitleaks.toml")])
        finally:
            os.chdir(original)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--history", action="store_true")
    args = parser.parse_args()
    if args.history:
        raise SystemExit(0 if run_scan(["git", ".", "--log-opts=--all"]) else 1)
    passed = scan_checkout()
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if event_path:
        event = json.loads(Path(event_path).read_text())
        if "pull_request" in event:
            start = revision(event["pull_request"]["base"]["sha"])
            end = revision(event["pull_request"]["head"]["sha"])
        else:
            end = revision(event.get("after"))
            start = revision(event.get("before"))
            if start == "0" * 40:
                default = event["repository"]["default_branch"]
                subprocess.run(["git", "check-ref-format", "--branch", default], check=True,
                               capture_output=True)
                ref = "refs/remotes/origin/" + default
                if subprocess.run(["git", "rev-parse", "--verify", ref],
                                  capture_output=True).returncode:
                    subprocess.run(["git", "fetch", "--no-tags", "origin",
                                    f"refs/heads/{default}:{ref}"], check=True, capture_output=True)
                start = revision(subprocess.check_output(
                    ["git", "merge-base", ref, end], text=True).strip())
        logopts = f"{start}..{end}"
        passed = run_scan(["git", ".", f"--log-opts={logopts}"]) and passed
    raise SystemExit(0 if passed else 1)
