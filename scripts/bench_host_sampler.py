#!/usr/bin/env python3
"""Host sampler for the Docling load benchmark (spec 0022 S1): cgroup v2 counters + optional nvidia-smi."""
import argparse
import csv
import os
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bench_docling_load import UsageError, check_output_root  # noqa: E402

HOST_FIELDS = ["ts", "cpu_usage_usec", "nr_throttled", "throttled_usec", "mem_current", "mem_peak",
               "oom_kill", "io_rbytes", "io_wbytes"]
GPU_QUERY = "timestamp,utilization.gpu,memory.used"
STOP = False


def kv(path):
    out = {}
    with open(path) as fh:
        for line in fh:
            parts = line.split()
            if len(parts) == 2:
                out[parts[0]] = int(parts[1])
    return out


def num(path):
    with open(path) as fh:
        return int(fh.read().strip())


def io_totals(path):
    r = w = 0
    try:
        with open(path) as fh:
            for line in fh:
                for tok in line.split()[1:]:
                    key, _, val = tok.partition("=")
                    if key == "rbytes":
                        r += int(val)
                    elif key == "wbytes":
                        w += int(val)
    except OSError:
        pass
    return r, w


def sample(cg):
    cpu, ev = kv(os.path.join(cg, "cpu.stat")), kv(os.path.join(cg, "memory.events"))
    r, w = io_totals(os.path.join(cg, "io.stat"))
    return [datetime.now(timezone.utc).isoformat(), cpu.get("usage_usec", 0), cpu.get("nr_throttled", 0),
            cpu.get("throttled_usec", 0), num(os.path.join(cg, "memory.current")),
            num(os.path.join(cg, "memory.peak")), ev.get("oom_kill", 0), r, w]


def open_new(path, mode="w"):
    return os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), mode, newline="")


def start_gpu(run_dir):
    exe = shutil.which("nvidia-smi")
    if not exe:
        print("warning: nvidia-smi not found, gpu.csv skipped", file=sys.stderr)
        return None, None
    fh = open_new(os.path.join(run_dir, "gpu.csv"))
    fh.write(GPU_QUERY.replace(".", "_") + "\n")
    fh.flush()
    proc = subprocess.Popen([exe, f"--query-gpu={GPU_QUERY}", "--format=csv,noheader,nounits", "-l", "1"],
                            stdout=fh, stderr=subprocess.DEVNULL)
    return proc, fh


def parse_args(argv):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cgroup", required=True, help="cgroup v2 directory of the worker")
    p.add_argument("--out", required=True, help="run directory under the benchmarks root")
    p.add_argument("--interval", type=float, default=1.0)
    p.add_argument("--duration", type=float, default=None)
    p.add_argument("--no-gpu", action="store_true")
    return p.parse_args(argv)


def run(args):
    run_dir = check_output_root(args.out)
    if not os.path.isfile(os.path.join(args.cgroup, "cpu.stat")):
        raise UsageError(f"{args.cgroup} is not a cgroup v2 directory")
    os.makedirs(run_dir, mode=0o700, exist_ok=True)
    peak_before = num(os.path.join(args.cgroup, "memory.peak"))
    t_start = datetime.now(timezone.utc).isoformat()
    proc, gpu_fh = (None, None) if args.no_gpu else start_gpu(run_dir)
    deadline = time.monotonic() + args.duration if args.duration is not None else None
    try:
        with open_new(os.path.join(run_dir, "host.csv")) as fh:
            wr = csv.writer(fh)
            wr.writerow(HOST_FIELDS)
            while not STOP:
                wr.writerow(sample(args.cgroup))
                fh.flush()
                if deadline is not None and time.monotonic() >= deadline:
                    break
                time.sleep(args.interval)
    finally:  # nvidia-smi must never outlive the sampler, even if the cgroup vanishes mid-run
        if proc:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
            gpu_fh.close()
        try:
            peak_after = num(os.path.join(args.cgroup, "memory.peak"))
        except OSError:
            peak_after = None
        with open_new(os.path.join(run_dir, "host_peak.csv")) as fh:
            wr = csv.writer(fh)
            wr.writerow(["t_start", "t_end", "memory_peak_before", "memory_peak_after"])
            wr.writerow([t_start, datetime.now(timezone.utc).isoformat(), peak_before, peak_after])


def _stop(*_):
    global STOP
    STOP = True


def main(argv=None):
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    try:
        run(parse_args(argv))
    except UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
