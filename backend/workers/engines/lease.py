"""
Leadership of the dispatcher, fenced by an epoch (spec 0003, Appendix E).

One row, `dispatcher_lease`. Taking it is a conditional UPDATE that bumps the
epoch, allowed only when nobody holds it or the holder stopped renewing for
15 s. Every placement re-reads the epoch in share mode (LOCK IN SHARE MODE) and
gives up if it is not its own; taking the lease needs the row exclusively, so a
leader that was replaced - a slow tick, a GC pause - can no longer write a
placement. The watchdog in the API takes the same lease for one round.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import or_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shared.models import DispatcherLease

logger = logging.getLogger(__name__)

LEASE_SECONDS = 15


def ensure_row(db: Session) -> None:
    """The single lease row (seeded by init_db; created here too for databases made otherwise)"""
    if db.get(DispatcherLease, 1) is None:
        try:
            db.add(DispatcherLease(id=1, epoch=0))
            db.commit()
        except IntegrityError:
            db.rollback()


def acquire(db: Session, holder: str, kind: str, now: Optional[datetime] = None) -> Optional[int]:
    """Become the leader if the lease is free or expired; returns the new epoch, or None"""
    now = now or datetime.utcnow()
    ensure_row(db)
    values = dict(epoch=DispatcherLease.epoch + 1, holder=holder, holder_kind=kind, renewed_at=now)
    if kind == "dispatcher":
        values["dispatcher_seen_at"] = now
    n = db.execute(
        update(DispatcherLease)
        .where(DispatcherLease.id == 1,
               or_(DispatcherLease.holder.is_(None), DispatcherLease.renewed_at.is_(None),
                   DispatcherLease.renewed_at < now - timedelta(seconds=LEASE_SECONDS)))
        .values(**values)
        .execution_options(synchronize_session=False)
    ).rowcount
    db.commit()
    if n != 1:
        return None
    epoch = db.query(DispatcherLease.epoch).filter(DispatcherLease.id == 1).scalar()
    logger.info(f"[ENGINES] {holder} ({kind}) leads the dispatcher with epoch {epoch}")
    return epoch


def renew(db: Session, epoch: int, holder: str, kind: str, now: Optional[datetime] = None) -> bool:
    """Keep the lease; False means it was taken over and this process must stop placing"""
    now = now or datetime.utcnow()
    values = dict(renewed_at=now)
    if kind == "dispatcher":
        values["dispatcher_seen_at"] = now
    n = db.execute(
        update(DispatcherLease)
        .where(DispatcherLease.id == 1, DispatcherLease.epoch == epoch, DispatcherLease.holder == holder)
        .values(**values)
        .execution_options(synchronize_session=False)
    ).rowcount
    db.commit()
    return n == 1


def release(db: Session, epoch: int) -> None:
    db.execute(update(DispatcherLease).where(DispatcherLease.id == 1, DispatcherLease.epoch == epoch)
               .values(holder=None).execution_options(synchronize_session=False))
    db.commit()


def holds(db: Session, epoch: int) -> bool:
    """Inside a placement transaction: is `epoch` still current? Read in share mode (fencing)."""
    current = (db.query(DispatcherLease.epoch).filter(DispatcherLease.id == 1)
               .with_for_update(read=True).scalar())
    return current == epoch


def state(db: Session) -> Optional[DispatcherLease]:
    return db.get(DispatcherLease, 1)
