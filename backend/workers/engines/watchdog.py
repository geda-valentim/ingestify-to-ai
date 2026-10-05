"""
The API's watchdog for the dispatcher (spec 0003, 4.4, defense 2).

With a route, local work also goes through the dispatcher. Every 15 s the API
process (always up while work comes in, unlike a worker whose slots page jobs
may hold) checks `dispatcher_seen_at`. When it is older than the route's
dispatcher_down_seconds it alerts and, for routes with dispatcher_fallback=
local_direct, takes the lease (a new epoch) for one round: sweeps local rows,
places at most capacity - in_flight(local) items on local steps (the tick's own
code), and hands draining routes back to today's path. The rest waits for the
dispatcher, within reach of remote steps. With `hold` it only alerts.

Without any route this is one SELECT on feature_routes per round.
"""

import logging
from datetime import datetime
from typing import Optional

from shared.engines import dispatch, routing
from shared.models import DispatcherLease
from workers.engines import dispatcher, sweeper

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 15
ALERT_EVERY_SECONDS = 300

_last_alert = {"at": None}


def watchdog_round(*, celery, session_factory=None, now: Optional[datetime] = None, redis_client=None,
                   alive=None) -> Optional[dispatcher.TickResult]:
    now = now or datetime.utcnow()
    db = dispatcher._session(session_factory)
    try:
        routes = routing.load_routes(db)
        lease_row = db.get(DispatcherLease, 1) if routes else None
        seen = lease_row.dispatcher_seen_at if lease_row else None
    finally:
        db.close()
    if not routes:
        return None
    down = [r for r in routes if dispatch.dispatcher_down(r, seen, now)]
    if not down:
        return None
    acting = [r for r in down if r.dispatcher_fallback == "local_direct" and r.has_local_step()]
    if _last_alert["at"] is None or (now - _last_alert["at"]).total_seconds() >= ALERT_EVERY_SECONDS:
        _last_alert["at"] = now
        logger.warning(
            f"[ENGINES] ALERT: dispatcher not seen since {seen or 'ever'} - routes "
            f"{', '.join(r.feature for r in down)}; "
            + ("placing local work from the API watchdog" if acting or any(not r.active for r in down)
               else "dispatcher_fallback=hold: items wait")
        )
    if not acting and all(r.active for r in down):
        return None
    sweeper.sweep(celery=celery, session_factory=session_factory, now=now, redis_client=redis_client)
    return dispatcher.run_tick(celery=celery, session_factory=session_factory, kind="watchdog", now=now,
                               local_only=True, alive=alive, redis_client=redis_client,
                               only_features={r.feature for r in acting})
