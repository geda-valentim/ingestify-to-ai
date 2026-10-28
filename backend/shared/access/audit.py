"""Audit rows of access administration (spec 0009)."""

from shared.models import AdminAudit


def audit(db, actor, action, target, after=None):
    db.add(
        AdminAudit(
            actor_user_id=actor,
            auth_method="jwt",
            action=action,
            target_type="access",
            target_id=str(target),
            after=after,
        )
    )
