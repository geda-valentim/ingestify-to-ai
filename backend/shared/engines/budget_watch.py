"""
A remote engine's budget over its period: alerts and exhaustion (spec 0003, 4.7-4.8).

Run after every remote settle, after each spend reconciliation and after a
benchmark, under the engine's row lock:

    soft      spent >= soft_pct % of limit_usd           -> alert, once per period
                                                             (alerted_soft_period)
    exhausted limit - min_remaining - spent < the median -> health `exhausted` until the
              cost of one item (or <= 0)                    next period starts; alert once
                                                             per period (alerted_hard_period)

`spent` is max(ledger, provider-reported), as for admission. Raising the limit
clears `exhausted` (store.set_budget); a new period clears it by itself
(health_until is the period's end). The dispatcher already refuses what does
not fit; `exhausted` also stops the engine from being tried at all - and
fill_first moves to the next account at once.
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from shared.engines import alerts, budget
from shared.models import Engine, EngineUsage

logger = logging.getLogger(__name__)

MEDIAN_WINDOW = 200
REASON_PREFIX = "BUDGET"


def median_item_cost(db: Session, engine_id: str) -> Optional[Decimal]:
    """Median actual cost of the engine's last 200 successful job attempts (None without any)"""
    costs = sorted(Decimal(str(c)) for c, in db.query(EngineUsage.actual_usd).filter(
        EngineUsage.engine_id == engine_id, EngineUsage.kind == "job", EngineUsage.status == "settled",
        EngineUsage.outcome == "succeeded", EngineUsage.actual_usd.isnot(None))
        .order_by(EngineUsage.finished_at.desc(), EngineUsage.id.desc()).limit(MEDIAN_WINDOW).all())
    if not costs:
        return None
    middle = len(costs) // 2
    return costs[middle] if len(costs) % 2 else (costs[middle - 1] + costs[middle]) / 2


def _evaluate(db: Session, engine: Engine, now: datetime) -> List[Dict]:
    """Mutates the locked engine row; returns the alerts to send after the commit"""
    if engine.adapter_type == "local" or engine.limit_usd is None:
        return []
    period = budget.period_start(engine, now)
    limit = Decimal(str(engine.limit_usd))
    spent = budget.spent(db, engine, period)
    out = []
    soft_pct = int(engine.soft_pct or 80)
    figures = {"period": period.isoformat(), "spent_usd": float(spent), "limit_usd": float(limit),
               "soft_pct": soft_pct}
    if engine.alerted_soft_period != period and spent >= limit * Decimal(soft_pct) / 100:
        engine.alerted_soft_period = period
        out.append(dict(event=alerts.BUDGET_SOFT, engine=engine.slug, details=figures,
                        message=f"{engine.slug} spent US$ {spent:.4f} of US$ {limit} this period "
                                f"({soft_pct}% alert)"))

    remaining = limit - Decimal(str(engine.min_remaining_usd or 0)) - spent
    median = median_item_cost(db, engine.id)
    if remaining <= 0 or (median is not None and remaining < median):
        until = budget.period_end(engine, now)
        reason = (f"{REASON_PREFIX}: US$ {max(remaining, Decimal(0)):.4f} left this period, below one item "
                  f"(median US$ {median if median is not None else '-'}); until {until:%Y-%m-%d %H:%M} UTC")
        healthy = engine.health in ("unknown", "healthy", "degraded") or (
            engine.health_until is not None and engine.health_until <= now)
        if healthy or (engine.health == "exhausted" and (engine.health_reason or "").startswith(REASON_PREFIX)):
            engine.health, engine.health_reason, engine.health_until = "exhausted", reason[:1000], until
        if engine.alerted_hard_period != period:
            engine.alerted_hard_period = period
            out.append(dict(event=alerts.BUDGET_EXHAUSTED, engine=engine.slug,
                            details={**figures, "remaining_usd": float(remaining),
                                     "median_item_usd": float(median) if median is not None else None,
                                     "until": until.isoformat()},
                            message=f"{engine.slug} is exhausted until {until:%Y-%m-%d %H:%M} UTC: "
                                    f"US$ {max(remaining, Decimal(0)):.4f} left"))
    return out


def check(engine_id: str, *, session_factory=None, now: Optional[datetime] = None) -> List[Dict]:
    """Evaluate one engine under its row lock; sends (and returns) the alerts it raised"""
    from shared.engines import ledger

    now = now or datetime.utcnow()

    def work(db: Session):
        engine = db.query(Engine).filter(Engine.id == engine_id).with_for_update().first()
        return _evaluate(db, engine, now) if engine is not None else []

    try:
        pending = ledger.run_txn(session_factory, work)
    except Exception as e:  # never fail a settle over an alert
        logger.warning(f"[ENGINES] Budget check of engine {engine_id} failed: {type(e).__name__}: {e}")
        return []
    return [alerts.alert(p["event"], p["engine"], p["message"], p["details"], now=now) for p in pending]


def quota_exhausted(engine_id: str, detail: str, *, session_factory=None, now: Optional[datetime] = None) -> None:
    """The provider refused for money (spending limit, workspace disabled): one hard alert per period"""
    from shared.engines import ledger

    now = now or datetime.utcnow()

    def work(db: Session):
        engine = db.query(Engine).filter(Engine.id == engine_id).with_for_update().first()
        if engine is None:
            return None
        period = budget.period_start(engine, now)
        if engine.alerted_hard_period == period:
            return None
        engine.alerted_hard_period = period
        return engine.slug, period

    try:
        hit = ledger.run_txn(session_factory, work)
    except Exception as e:
        logger.warning(f"[ENGINES] Quota alert of engine {engine_id} failed: {type(e).__name__}")
        return
    if hit:
        alerts.alert(alerts.QUOTA_EXHAUSTED, hit[0], f"the provider refused for money: {detail[:200]}",
                     {"period": hit[1].isoformat()}, now=now)
