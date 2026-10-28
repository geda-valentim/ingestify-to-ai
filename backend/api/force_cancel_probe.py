"""What the API sees of an admission ticket's holder when a force_cancel is planned (spec 0007
§4.5): one read-only `inspect active` of the holders' Celery nodes, 2 s at most, judged with the
drain's own rule (workers/engine_control/orphan_tickets). Registered once at import.
"""

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

from shared.engine_control import force_cancel

INSPECT_TIMEOUT_SECONDS = 2.0  # end to end: connection, publish, retries and replies
# The inspect runs here with a hard wall-clock deadline: Celery's own timeout only bounds the
# wait for replies, not reaching a broker that is down. Two workers at most: with the broker
# hung, later plans queue behind them and time out as "unknown" too, threads never pile up.
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="force-cancel-probe")


def holder_verdicts(holders):
    """{holder: {"verdict", "pid", "host"}}: alive, absent (its node answered without it),
    node_silent, legacy_holder (no pid and node to look for: an old `task:<id>`), or unknown
    (a live session's holder, or no broker answer at all)."""
    from workers.engine_control.orphan_tickets import _still_running, active_by_node, parse_task_holder

    parsed = {h: parse_task_holder(h) for h in holders}
    nodes = {p[2] for p in parsed.values() if p}
    try:
        future = _pool.submit(active_by_node, nodes, timeout=INSPECT_TIMEOUT_SECONDS) if nodes else None
        active, answered = (future.result(timeout=INSPECT_TIMEOUT_SECONDS) if future else {}), True
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
