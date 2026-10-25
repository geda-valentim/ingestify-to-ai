"""Host sampler tests: fake cgroup files in tmp_path only, never the real host."""
import csv
import importlib.util
import os
import stat
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if not (SCRIPTS / "bench_host_sampler.py").exists():
    pytest.skip("scripts/ not mounted (backend-only container)", allow_module_level=True)
import sys

sys.path.insert(0, str(SCRIPTS))
import bench_docling_load as load  # noqa: E402

spec = importlib.util.spec_from_file_location("bench_host_sampler", SCRIPTS / "bench_host_sampler.py")
hs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hs)


@pytest.fixture
def env(tmp_path, monkeypatch):
    cg = tmp_path / "cg"
    cg.mkdir()
    (cg / "cpu.stat").write_text("usage_usec 500\nuser_usec 1\nnr_throttled 3\nthrottled_usec 70\n")
    (cg / "memory.current").write_text("1000\n")
    (cg / "memory.peak").write_text("2000\n")
    (cg / "memory.events").write_text("low 0\noom_kill 1\n")
    (cg / "io.stat").write_text("8:0 rbytes=10 wbytes=5 rios=1\n8:16 rbytes=1 wbytes=2\n")
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setattr(load, "ALLOWED_ROOT", str(root))
    monkeypatch.setattr(load, "ROOT_DEVICE_PATH", "/proc")  # different st_dev than tmp_path
    monkeypatch.setattr(hs, "STOP", False)
    monkeypatch.setenv("PATH", str(tmp_path / "nobin"))
    return cg, root


def test_samples_and_peaks(env):
    cg, root = env
    out = root / "run1"
    assert hs.main(["--cgroup", str(cg), "--out", str(out), "--duration", "0", "--interval", "0.01"]) == 0
    rows = list(csv.DictReader(open(out / "host.csv")))
    assert rows[0]["cpu_usage_usec"] == "500" and rows[0]["nr_throttled"] == "3"
    assert rows[0]["oom_kill"] == "1" and rows[0]["io_rbytes"] == "11" and rows[0]["io_wbytes"] == "7"
    peak = list(csv.DictReader(open(out / "host_peak.csv")))[0]
    assert peak["memory_peak_before"] == "2000" and peak["memory_peak_after"] == "2000"
    assert not (out / "gpu.csv").exists()
    assert stat.S_IMODE((out / "host.csv").stat().st_mode) == 0o600
    assert stat.S_IMODE(out.stat().st_mode) == 0o700


def test_fake_nvidia_smi(env, tmp_path, monkeypatch):
    cg, root = env
    bindir = tmp_path / "bin"
    bindir.mkdir()
    smi = bindir / "nvidia-smi"
    smi.write_text("#!/bin/sh\necho '2026/01/01 00:00:00.000, 55, 1234'\nsleep 5\n")
    smi.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}:/usr/bin:/bin")
    out = root / "run2"
    assert hs.main(["--cgroup", str(cg), "--out", str(out), "--duration", "0.5", "--interval", "0.1"]) == 0
    assert "55, 1234" in (out / "gpu.csv").read_text()


def test_rejects_outside_root_and_bad_cgroup(env, tmp_path):
    cg, root = env
    assert hs.main(["--cgroup", str(cg), "--out", str(tmp_path / "elsewhere"), "--duration", "0"]) == 2
    assert hs.main(["--cgroup", str(tmp_path), "--out", str(root / "r3"), "--duration", "0"]) == 2


def test_gpu_process_is_stopped_when_sampling_fails(env, tmp_path, monkeypatch):
    cg, root = env
    bindir, pidfile = tmp_path / "bin", tmp_path / "smi.pid"
    bindir.mkdir()
    (bindir / "nvidia-smi").write_text(f"#!/bin/sh\necho $$ > {pidfile}\nexec sleep 30\n")
    (bindir / "nvidia-smi").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}:/usr/bin:/bin")
    real, calls = hs.sample, []

    def flaky(cg):  # first sample works, then the cgroup vanishes (leaves time for nvidia-smi to start)
        if calls:
            raise OSError("cgroup vanished")
        calls.append(1)
        return real(cg)

    monkeypatch.setattr(hs, "sample", flaky)
    out = root / "run4"
    with pytest.raises(OSError):
        hs.main(["--cgroup", str(cg), "--out", str(out), "--interval", "0.5"])
    with pytest.raises(ProcessLookupError):
        os.kill(int(pidfile.read_text()), 0)
    assert (out / "host_peak.csv").exists()
