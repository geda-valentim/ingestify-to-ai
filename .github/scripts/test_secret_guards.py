"""Prove fixture exceptions do not exempt real credentials in the same file."""
import os
import secrets
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory() as temp:
    path = Path(temp) / "backend/tests/test_engine_secrets.py"
    path.parent.mkdir(parents=True)
    path.write_text('api_key = "' + secrets.token_urlsafe(40) + '"\n')
    result = subprocess.run(["gitleaks", "dir", ".", "--config", str(root / ".gitleaks.toml"),
        "--redact", "--no-banner", "--log-level", "error"], cwd=temp, capture_output=True)
    if result.returncode != 1:
        raise SystemExit("A new synthetic secret escaped detection in a fixture file")
print("Exact fixture exceptions preserve detection of new credentials")
