"""
The local executor's side of a reservation: while process_conversion runs a
routed item (usage_id set), a thread renews the usage row's heartbeat every 15 s.
The sweeper gives up a `running` row whose heartbeat is older than
local_stale_seconds (90): its process died (OOM, task_time_limit, container
removed) and the item goes back to the backlog (spec 0003, 4.7 step 3).
"""

import logging
import threading

from shared.engines import ledger

logger = logging.getLogger(__name__)

HEARTBEAT_SECONDS = 15


class UsageHeartbeat:
    def __init__(self, usage_id: int, holder: str, interval: float = HEARTBEAT_SECONDS, session_factory=None):
        self.usage_id = usage_id
        self.holder = holder
        self.interval = interval
        self.session_factory = session_factory
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name=f"usage-heartbeat-{usage_id}", daemon=True)

    def start(self) -> "UsageHeartbeat":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                if not ledger.heartbeat(self.usage_id, self.holder, session_factory=self.session_factory):
                    # Given up by the sweeper: keep working, the output still counts (the
                    # next attempt finds the job COMPLETED and settles without running)
                    logger.warning(f"[ENGINES] Usage {self.usage_id} is no longer ours; finishing anyway")
                    return
            except Exception as e:  # a missed beat is recovered by the next one
                logger.warning(f"[ENGINES] Heartbeat of usage {self.usage_id} failed: {e}")
