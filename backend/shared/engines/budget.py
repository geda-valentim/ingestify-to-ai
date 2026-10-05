"""
Money an engine may still commit, from the ledger (spec 0003, section 4.7).

    admits <=> max(ledger, provider_reported) + reserved + estimate <= limit - min_remaining
               and spend_cap of the step: settled + reserved in the window + estimate <= usd
               and (remote_allowed_for=all => the user's settled + reserved + estimate <= their limit)

The local engine costs nothing, so only capacity limits it. Values are Decimal;
every sum is read under the engine's row lock by the caller.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import Session

from shared.models import Engine, EngineUsage

ZERO = Decimal("0")
IN_FLIGHT = ("reserved", "spawning", "running")


def is_local(engine: Engine) -> bool:
    return engine.adapter_type == "local"


def period_start(engine: Engine, now: datetime) -> date:
    """First day of the engine's budget period containing `now` (UTC naive), in its own time zone"""
    try:
        tz = ZoneInfo(engine.period_tz or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    local = now.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz)
    anchor = min(max(int(engine.period_anchor_day or 1), 1), 28)
    if local.day >= anchor:
        return date(local.year, local.month, anchor)
    previous = date(local.year, local.month, 1) - timedelta(days=1)
    return date(previous.year, previous.month, anchor)


def _dec(value) -> Decimal:
    return ZERO if value is None else Decimal(str(value))


def settled(db: Session, engine_id: str, period: date) -> Decimal:
    return _dec(db.query(func.sum(EngineUsage.actual_usd)).filter(
        EngineUsage.engine_id == engine_id, EngineUsage.period_start == period,
        EngineUsage.status == "settled").scalar())


def reserved(db: Session, engine_id: str, period: date) -> Decimal:
    return _dec(db.query(func.sum(EngineUsage.reserved_usd)).filter(
        EngineUsage.engine_id == engine_id, EngineUsage.period_start == period,
        EngineUsage.status.in_(IN_FLIGHT)).scalar())


def spent(db: Session, engine: Engine, period: date) -> Decimal:
    """What counts as already spent: the larger of our ledger and what the provider reports"""
    ledger = settled(db, engine.id, period)
    reported = _dec(engine.provider_reported_usd) if engine.provider_reported_period == period else ZERO
    return max(ledger, reported)


def headroom(db: Session, engine: Engine, period: date, *, include_reserved: bool = True) -> Optional[Decimal]:
    """limit - min_remaining - spent [- reserved]; None for a remote engine without a limit (never admits)"""
    if engine.limit_usd is None:
        return None
    room = _dec(engine.limit_usd) - _dec(engine.min_remaining_usd) - spent(db, engine, period)
    if include_reserved:
        room -= reserved(db, engine.id, period)
    return room


def admits(db: Session, engine: Engine, estimate: Decimal, period: date) -> bool:
    if is_local(engine):
        return True
    room = headroom(db, engine, period)
    return room is not None and estimate <= room


def could_ever_admit(db: Session, engine: Engine, estimate: Decimal, period: date) -> bool:
    """Would fit once the engine's in-flight work settled (the skip rule, R7)"""
    if is_local(engine):
        return True
    room = headroom(db, engine, period, include_reserved=False)
    return room is not None and estimate <= room


def window_start(window: str, engine: Engine, now: datetime) -> datetime:
    if window == "day":
        return datetime(now.year, now.month, now.day)
    start = period_start(engine, now)
    return datetime(start.year, start.month, start.day)


def committed_in_window(db: Session, engine: Engine, feature: str, since: datetime, *,
                        include_reserved: bool = True) -> Decimal:
    """settled [+ reserved] of this engine and feature since a moment"""
    total = _dec(db.query(func.sum(EngineUsage.actual_usd)).filter(
        EngineUsage.engine_id == engine.id, EngineUsage.feature == feature,
        EngineUsage.status == "settled", EngineUsage.created_at >= since).scalar())
    if include_reserved:
        total += _dec(db.query(func.sum(EngineUsage.reserved_usd)).filter(
            EngineUsage.engine_id == engine.id, EngineUsage.feature == feature,
            EngineUsage.status.in_(IN_FLIGHT), EngineUsage.created_at >= since).scalar())
    return total


def spend_cap_ok(db: Session, engine: Engine, feature: str, cap: Optional[dict], estimate: Decimal,
                 now: datetime, *, include_reserved: bool = True) -> bool:
    """A step's spend_cap counts reservations too (R10); without them it is the skip rule's "once settled" view"""
    if not cap or is_local(engine):
        return True
    since = window_start(cap["window"], engine, now)
    committed = committed_in_window(db, engine, feature, since, include_reserved=include_reserved)
    return committed + estimate <= _dec(cap["usd"])


def user_committed(db: Session, user_id: str, period: date) -> Decimal:
    settled_sum = db.query(func.sum(EngineUsage.actual_usd)).filter(
        EngineUsage.user_id == user_id, EngineUsage.period_start == period, EngineUsage.status == "settled").scalar()
    reserved_sum = db.query(func.sum(EngineUsage.reserved_usd)).filter(
        EngineUsage.user_id == user_id, EngineUsage.period_start == period,
        EngineUsage.status.in_(IN_FLIGHT)).scalar()
    return _dec(settled_sum) + _dec(reserved_sum)
