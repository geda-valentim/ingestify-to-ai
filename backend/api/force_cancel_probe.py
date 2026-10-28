"""What the API sees of an admission ticket's holder when a force_cancel is planned (spec 0007
§4.5): one read-only `inspect active` of the holders' Celery nodes, 2 s at most, judged with the
drain's own rule (workers/engine_control/orphan_tickets). Registered once at import.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

from shared.engine_control import force_cancel

INSPECT_TIMEOUT_SECONDS = 2.0  # end to end: connection, publish, retries and replies
# Celery waits its whole timeout when a node is silent; it stops collecting this much before the
# deadline, so the replies of the nodes that did answer come back before the wall-clock wait ends.
REPLY_MARGIN_SECONDS = 0.5
# The inspect runs here with a hard wall-clock deadline: Celery's own timeout only bounds the
# wait for replies, not reaching a broker that is down. Two inspects in flight at most: with
# both slots held by a hung broker, a new plan answers "unknown" at once, without queueing
# work (the executor's queue is unbounded); a slot is freed only when its inspect returns.
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="force-cancel-probe")
_slots = threading.BoundedSemaphore(2)


def _inspect(active_by_node, nodes):
    deadline = time.monotonic() + INSPECT_TIMEOUT_SECONDS  # one budget for the whole probe
    if not _slots.acquire(blocking=False):
        raise FutureTimeout("both probe slots are held by earlier inspects")
    try:
        replies_for = max(deadline - time.monotonic() - REPLY_MARGIN_SECONDS, 0.0)
        future = _pool.submit(active_by_node, nodes, timeout=replies_for)
    except Exception:
        _slots.release()
        raise
    future.add_done_callback(lambda _: _slots.release())
    return future.result(timeout=max(deadline - time.monotonic(), 0.0))


def holder_verdicts(holders):
    """{holder: {"verdict", "pid", "host"}}: alive, absent (its node answered without it),
    node_silent, legacy_holder (no pid and node to look for: an old `task:<id>`), or unknown
    (a live session's holder, or no broker answer at all)."""
    from workers.engine_control.orphan_tickets import _still_running, active_by_node, parse_task_holder

    parsed = {h: parse_task_holder(h) for h in holders}
    nodes = {p[2] for p in parsed.values() if p}
    try:
        active, answered = (_inspect(active_by_node, nodes) if nodes else {}), True
    except (FutureTimeout, Exception):
        active, answered = {}, False
    out = {}
    for holder, p in parsed.items():
        if p is None:
            verdict = "unknown" if holder.startswith("live:") else "legacy_holder"
            out[holder] = {"verdict": verdict, "pid": None, "host": None}
            continue
        task_id, pid, node = p
        if not answered:
            verdict = "unknown"
        elif node not in active:
            verdict = "node_silent"
        else:
            verdict = "alive" if _still_running(active[node], task_id, pid) else "absent"
        out[holder] = {"verdict": verdict, "pid": pid, "host": node.split("@", 1)[-1]}
    return out


force_cancel.set_holder_probe(holder_verdicts)
