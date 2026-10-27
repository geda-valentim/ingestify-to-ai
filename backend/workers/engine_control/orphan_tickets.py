"""Admission tickets whose holder process is gone (spec 0007, section 4.5).

A task releases its ticket in `finally`, which never runs when the process is
killed (OOM, SIGKILL, container restart). Such a ticket would hold a drain until
DRAIN_TIMEOUT. A ticket is released here only on positive evidence: the Celery
node that ran the task answers, and that task is no longer active in that
process. A node that does not answer proves nothing, and age alone never
releases a ticket.
"""

import os
from datetime import timedelta

from shared.engine_control.models import ControlAdmission
from shared.engine_control.service import now

TASK_PREFIX = "task:"
HOLDER_LIMIT = 128  # ControlAdmission.holder
# A prefork parent learns asynchronously that its child started a task, so a
# brand-new ticket may not be in `active()` yet. Younger tickets are not judged.
# This is a precondition for looking, never a reason to release.
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
    if len(parts) != 3 or not parts[0] or not parts[1].isdigit() or not parts[2]:
        return None
    return parts[0], int(parts[1]), parts[2]


def active_by_node(nodes, timeout=1.0):
    """{node: [(task_id, pid), ...]} for the nodes that answered. Missing node = unknown."""
    from workers.celery_app import celery_app

    replies = celery_app.control.inspect(destination=sorted(nodes), timeout=timeout).active() or {}
    return {
        node: [(t.get("id"), t.get("worker_pid")) for t in (tasks or [])]
        for node, tasks in replies.items()
        if isinstance(tasks, list)
    }


def release_dead(session_factory, resource_keys, inspect_active=None):
    """Release open tickets on these resources whose task process is provably gone. Returns how many."""
    with session_factory() as db:
        rows = (
            db.query(ControlAdmission.id, ControlAdmission.holder)
            .filter(
                ControlAdmission.resource_key.in_(resource_keys),
                ControlAdmission.released_at.is_(None),
                ControlAdmission.created_at < now() - timedelta(seconds=ACCEPT_GRACE_SECONDS),
            )
            .all()
        )
    holders = {row.id: parse_task_holder(row.holder) for row in rows}
    holders = {ticket: h for ticket, h in holders.items() if h}
    if not holders:
        return 0
    try:
        active = (inspect_active or active_by_node)({node for _, _, node in holders.values()})
    except Exception:
        return 0  # No broker, no evidence: keep waiting.
    dead = [
        ticket
        for ticket, (task_id, pid, node) in holders.items()
        if node in active and (task_id, pid) not in active[node]
    ]
    if not dead:
        return 0
    with session_factory() as db:
        released = (
            db.query(ControlAdmission)
            .filter(ControlAdmission.id.in_(dead), ControlAdmission.released_at.is_(None))
            .update({"released_at": now()}, synchronize_session=False)
        )
        db.commit()
    return released
