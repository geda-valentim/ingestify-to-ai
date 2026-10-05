"""
Import remote engine accounts (spec 0003): parse them, then create or update one
PAUSED engine per account, idempotently by slug, credentials sealed to the
public key. Used by scripts/engines.py; nothing here prints or logs a secret.
"""

import hashlib
from dataclasses import dataclass
from typing import Dict, List, Optional

from shared.engines.redact import register_secret
from shared.engines.sealing import mask, seal

MAX_ACCOUNTS = 19


@dataclass
class Account:
    slug: str
    display_name: str
    token_id: str
    token_secret: str

    @property
    def fingerprint(self) -> str:
        # Identifies the credentials without revealing them (the secret is high-entropy)
        return hashlib.sha256(f"{self.token_id}:{self.token_secret}".encode()).hexdigest()[:16]

    def masked(self) -> Dict[str, object]:
        return {
            "token_id": mask(self.token_id, "last4"),
            "token_secret": mask(self.token_secret, "none"),
            "fingerprint": self.fingerprint,
        }


def accounts_from_env(values: Dict[str, Optional[str]], prefix: str) -> List[Account]:
    """Accounts {prefix}{N}_ID/_SECRET(/_NAME) for N = 1..19, in order"""
    accounts = []
    for n in range(1, MAX_ACCOUNTS + 1):
        token_id = (values.get(f"{prefix}{n}_ID") or "").strip()
        token_secret = (values.get(f"{prefix}{n}_SECRET") or "").strip()
        if not token_id and not token_secret:
            continue
        if not token_id or not token_secret:
            raise SystemExit(f"Account {n}: both {prefix}{n}_ID and {prefix}{n}_SECRET are required")
        name = (values.get(f"{prefix}{n}_NAME") or "").strip() or f"Modal account {n}"
        accounts.append(Account(f"modal_{n}", f"Modal {n} ({name})", token_id, token_secret))
    return accounts


def accounts_from_modal_toml(text: str) -> List[Account]:
    """One account per [profile] with token_id and token_secret"""
    import tomllib

    accounts = []
    for n, (profile, entry) in enumerate(tomllib.loads(text).items(), start=1):
        if isinstance(entry, dict) and entry.get("token_id") and entry.get("token_secret"):
            accounts.append(Account(f"modal_{n}", f"Modal {n} ({profile})", entry["token_id"], entry["token_secret"]))
    return accounts


def plan_and_apply(db, accounts: List[Account], public_key: str, limit_usd: Optional[float], apply: bool) -> List[dict]:
    """
    Create or update one paused engine per account, idempotently by slug. Returns
    the plan rows; writes (and audits) them only when `apply` is set.
    """
    from datetime import datetime
    from decimal import Decimal

    from shared.models import AdminAudit, Engine

    rows = []
    for account in accounts:
        register_secret(account.token_id)
        register_secret(account.token_secret)
        engine = db.query(Engine).filter(Engine.slug == account.slug).first()
        if engine is None:
            action = "create"
        elif (engine.credentials_masked or {}).get("fingerprint") != account.fingerprint:
            action = "update-credentials"
        else:
            action = "unchanged"
        if limit_usd is not None and engine is not None and engine.limit_usd != Decimal(str(limit_usd)):
            action = "update-limit" if action == "unchanged" else action + "+limit"
        rows.append({
            "slug": account.slug,
            "name": account.display_name,
            "token_id": f"…{account.token_id[-4:]}",
            "limit_usd": limit_usd if limit_usd is not None else (engine.limit_usd if engine else None),
            "action": action,
        })
        if not apply or action == "unchanged":
            continue

        before = None
        if engine is None:
            engine = Engine(slug=account.slug, display_name=account.display_name, adapter_type="modal",
                            config={"features": {}}, deployments={}, status="paused", credentials_masked={})
            db.add(engine)
            db.flush()  # the id is part of what the credentials are sealed to
        else:
            before = {"status": engine.status, "limit_usd": str(engine.limit_usd), "credentials": engine.credentials_masked}

        if "create" in action or "credentials" in action:
            blob, kid = seal({"token_id": account.token_id, "token_secret": account.token_secret}, public_key, engine.id)
            engine.credentials_sealed = blob
            engine.credentials_key_id = kid
            engine.credentials_masked = account.masked()
            engine.credentials_updated_at = datetime.utcnow()
            engine.credentials_updated_by = "cli"
        if limit_usd is not None:
            engine.limit_usd = Decimal(str(limit_usd))
        engine.status = "paused"  # imported engines are never active until an admin activates them
        engine.version = (engine.version or 0) + 1
        db.add(AdminAudit(
            auth_method="cli", action=f"engine.import.{action}", target_type="engine", target_id=engine.id,
            before=before,
            after={"status": "paused", "limit_usd": str(engine.limit_usd), "credentials": engine.credentials_masked},
        ))
    if apply:
        db.commit()
    return rows
