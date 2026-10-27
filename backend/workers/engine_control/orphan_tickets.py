"""Admission tickets whose holder process is gone (spec 0007, section 4.5).

A task releases its ticket in `finally`, which never runs when the process is
killed (OOM, SIGKILL, container restart). Such a ticket would hold a drain until
DRAIN_TIMEOUT. A ticket is released here only on positive evidence: the Celery
node that ran the task answers, and that task is no longer active in that
process. A node that does not answer proves nothing, and age alone never
releases a ticket.

Node names must be unique per process tree (`-n name@%h`, one container each):
`inspect` merges replies by node name, so two workers sharing a name could
answer for each other.
"""

import os
import time

from shared.engine_control.models import ControlAdmission
from shared.engine_control.service import now

TASK_PREFIX = "task:"
HOLDER_LIMIT = 128  # ControlAdmission.holder
# A prefork parent learns asynchronously that its child started a task, so a
# brand-new ticket may not be in `active()` yet. A ticket is judged only after
# this drain has seen it open for this long, by its own clock. This is a
# precondition for looking, never a reason to release.
ACCEPT_GRACE_SECONDS = 30


def task_holder(task_id, hostname, pid=None):
    """`task:<id>|<pid>|<node>`, or plain `task:<id>` when it cannot name its process."""
    plain = f"{TASK_PREFIX}{task_id}"
    if not task_id or not hostname:
        return plain
    holder = f"{plain}|{pid or os.getpid()}|{hostname}"
    return holder if len(holder) <= HOLDER_LIMIT else plain


def parse_task_holder(holder):
    """(task_id, pid, node) for a reconcilable task holder, else None."""
    if not holder.startswith(TASK_PREFIX):
        return None
    parts = holder[len(TASK_PREFIX):].split("|", 2)
    if len(parts) != 3 or not parts[0] or not parts[1].isdecimal() or not parts[2]:
        return None
    return parts[0], int(parts[1]), parts[2]


def active_by_node(nodes, timeout=1.0):
    """{node: [(task_id, pid), ...]} for the nodes that answered. Missing node = unknown."""
    from workers.celery_app import celery_app

    replies = celery_app.control.inspect(destination=sorted(nodes), timeout=timeout).active() or {}
    return {
        node: [(t.get("id"), t.get("worker_pid")) for t in tasks]
        for node, tasks in replies.items()
        if isinstance(tasks, list)  # {"error": ...} is no answer
    }


def open_tickets(db, resource_keys):
    return (
        db.query(ControlAdmission.id, ControlAdmission.holder)
        .filter(
            ControlAdmission.resource_key.in_(resource_keys),
            ControlAdmission.released_at.is_(None),
        )
        .order_by(ControlAdmission.created_at)
        .all()
    )


def release_dead(session_factory, resource_keys, first_seen, inspect_active=None, clock=time.monotonic):
    """Release open tickets on these resources whose task process is provably gone.

    Returns the distinct holders it released, for the operation's audit trail.

    `first_seen` maps ticket id -> when this drain first saw it open; the caller
    keeps it between calls.
    """
    with session_factory() as db:
        rows = open_tickets(db, resource_keys)
    stamp = clock()
    holders, holder_of = {}, {row.id: row.holder for row in rows}
    for row in rows:
        seen = first_seen.setdefault(row.id, stamp)
        parsed = parse_task_holder(row.holder)
        if parsed and stamp - seen >= ACCEPT_GRACE_SECONDS:
            holders[row.id] = parsed
    if not holders:
        return []
    try:
        active = (inspect_active or active_by_node)({node for _, _, node in holders.values()})
    except Exception:
        return []  # No broker, no evidence: keep waiting.
    dead = [
        ticket
        for ticket, (task_id, pid, node) in holders.items()
        if node in active and not _still_running(active[node], task_id, pid)
    ]
    if not dead:
        return []
    released = []
    with session_factory() as db:
        # Row by row: only what this call released goes to the audit trail, never a
        # ticket its own `finally` released meanwhile.
        for ticket in dead:
            changed = (
                db.query(ControlAdmission)
                .filter(ControlAdmission.id == ticket, ControlAdmission.released_at.is_(None))
                .update({"released_at": now()}, synchronize_session=False)
            )
            if changed:
                released.append(holder_of[ticket])
        db.commit()
    return list(dict.fromkeys(released))


def _still_running(active, task_id, pid):
    """A reply without the process id cannot clear that task."""
    return any(tid == task_id and wpid in (pid, None) for tid, wpid in active)


def residual(session_factory, resource_keys, limit=5):
    """How many tickets still block a drain, and the oldest distinct holders, for the timeout report."""
    with session_factory() as db:
        rows = open_tickets(db, resource_keys)
    # One task holds a ticket per resource; list each holder once.
    return len(rows), list(dict.fromkeys(row.holder for row in rows))[:limit]
