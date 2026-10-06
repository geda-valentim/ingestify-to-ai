"""Bounded progressive subprocess output with line buffering before redaction."""

import os
import selectors
import subprocess
import time
from shared.engines.redact import redact


def stream_run(
    argv, *, env, cwd, capture_output=True, text=True, timeout=3600, context=None
):
    # Keep the existing deploy helper's injected `run` signature for regression tests.
    proc = subprocess.Popen(
        argv,
        env=env,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    start = time.monotonic()
    tail = []
    line = bytearray()
    dropping = False
    sel = selectors.DefaultSelector()
    sel.register(proc.stdout, selectors.EVENT_READ)

    def emit():
        nonlocal line, dropping
        if dropping:
            message = "[linha longa omitida]"
        else:
            message = redact(line.decode("utf-8", errors="replace"))
        line = bytearray()
        dropping = False
        tail.append(message)
        if len(tail) > 100:
            tail.pop(0)
        if context:
            context.log(message)

    try:
        while sel.get_map():
            if context:
                context.check()
            if time.monotonic() - start > timeout:
                raise TimeoutError("PROCESS_DEADLINE")
            for key, _ in sel.select(0.25):
                chunk = os.read(key.fileobj.fileno(), 4096)
                if not chunk:
                    sel.unregister(key.fileobj)
                    if line or dropping:
                        emit()
                    continue
                # Never persist partial secret fragments. Oversized lines are dropped entirely.
                for byte in chunk:
                    if byte in (10, 13):
                        if line or dropping:
                            emit()
                    elif not dropping:
                        line.append(byte)
                        if len(line) > 8192:
                            line.clear()
                            dropping = True
        return subprocess.CompletedProcess(
            argv, proc.wait(timeout=5), "\n".join(tail), ""
        )
    except BaseException:
        import signal

        os.killpg(proc.pid, signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
        raise
    finally:
        sel.close()
        proc.stdout.close()
