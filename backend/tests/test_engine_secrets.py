"""
Engine credentials (spec 0003, slice 2): sealed at rest, redacted in logs, imported safely.

The API and the import CLI only hold the public key, so they can seal but never
open; only worker-remote holds the private key. A sealed blob is bound to its
engine, so it cannot be moved onto another engine's row. No token ever reaches
a log line, a traceback or the CLI's output.
"""

import io
import logging
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from shared.database import Base
from shared.engines import importer, redact, sealing
from shared.models import AdminAudit, Engine

TOKEN_ID = "ak-AbCdEfGh1234567890"
TOKEN_SECRET = "as-ZyXwVuTs0987654321QwErTy"


@pytest.fixture
def keys():
    public, private = sealing.generate_keypair()
    return public, private


# --- sealing --------------------------------------------------------------------------


def test_sealed_credentials_open_only_with_the_private_key(keys):
    public, private = keys
    blob, kid = sealing.seal({"token_id": TOKEN_ID, "token_secret": TOKEN_SECRET}, public, "engine-1")

    assert TOKEN_SECRET.encode() not in blob and TOKEN_ID.encode() not in blob
    assert kid == sealing.key_id(public)
    assert sealing.open_sealed(blob, [private], "engine-1", kid) == {
        "token_id": TOKEN_ID, "token_secret": TOKEN_SECRET,
    }


def test_each_seal_is_different(keys):
    public, _ = keys
    first, _ = sealing.seal({"a": "b"}, public, "engine-1")
    second, _ = sealing.seal({"a": "b"}, public, "engine-1")
    assert first != second  # fresh ephemeral key and nonce every time


def test_a_blob_moved_to_another_engine_does_not_open(keys):
    public, private = keys
    blob, kid = sealing.seal({"token_id": TOKEN_ID}, public, "engine-1")

    with pytest.raises(sealing.SealingError, match="wrong engine, or tampered"):
        sealing.open_sealed(blob, [private], "engine-2", kid)


def test_a_tampered_blob_does_not_open(keys):
    public, private = keys
    blob, kid = sealing.seal({"token_id": TOKEN_ID}, public, "engine-1")
    tampered = blob[:-1] + bytes([blob[-1] ^ 1])

    with pytest.raises(sealing.SealingError):
        sealing.open_sealed(tampered, [private], "engine-1", kid)


def test_rotation_finds_the_matching_private_key(keys):
    public, private = keys
    _, other_private = sealing.generate_keypair()
    blob, kid = sealing.seal({"x": "y"}, public, "e")

    assert sealing.open_sealed(blob, [other_private, private], "e", kid) == {"x": "y"}
    with pytest.raises(sealing.SealingError, match="No configured private key"):
        sealing.open_sealed(blob, [other_private], "e", kid)


def test_no_public_key_means_nothing_can_be_stored():
    with pytest.raises(sealing.SealingError, match="ENGINE_SECRETS_PUBLIC_KEY is not set"):
        sealing.seal({"x": "y"}, "", "e")


def test_mask_shows_at_most_the_last_four():
    assert sealing.mask(TOKEN_ID, "last4") == {"is_set": True, "hint": "7890"}
    assert sealing.mask(TOKEN_SECRET, "none") == {"is_set": True, "hint": None}
    assert sealing.mask("", "last4") == {"is_set": False, "hint": None}


# --- redaction ----------------------------------------------------------------------------


@pytest.mark.parametrize("text", [
    f"modal error for token {TOKEN_ID}",
    f"secret={TOKEN_SECRET} rejected",
    "Authorization: Bearer abcdefghijklmnopqrstuvwxyz",
    "token eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
    '{"api_key": "sk-proj-abcdefghijklmnop1234"}',
])
def test_credential_shapes_are_redacted(text):
    out = redact.redact(text)
    assert redact.MASK in out
    for secret in (TOKEN_ID, TOKEN_SECRET, "abcdefghijklmnopqrstuvwxyz", "sk-proj-abcdefghijklmnop1234"):
        assert secret not in out


def test_registered_values_are_redacted_whatever_their_shape():
    redact.register_secret("plain-looking-value-123")
    assert redact.redact("got plain-looking-value-123 back") == f"got {redact.MASK} back"


def test_ordinary_text_is_left_alone():
    text = "Transcribed 3726.0s with max_tokens=448, token_type=bearer, 85 segments"
    assert redact.redact(text) == text


def test_formatters_that_unpack_args_still_work():
    # uvicorn's access log does `client, method, path, version, status = record.args`
    redact.install_log_redaction()
    record = logging.getLogger("tests.access").makeRecord(
        "tests.access", logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:5000", "GET", f"/x?key={TOKEN_SECRET}", "1.1", 200), None,
    )
    client, method, path, version, status = record.args
    assert (client, method, version, status) == ("127.0.0.1:5000", "GET", "1.1", 200)
    assert TOKEN_SECRET not in path
    assert record.getMessage().endswith('HTTP/1.1" 200')


def test_an_exception_passed_as_an_argument_is_redacted():
    redact.install_log_redaction()
    record = logging.getLogger("tests.args").makeRecord(
        "tests.args", logging.ERROR, __file__, 1, "deploy failed: %s", (RuntimeError(f"bad {TOKEN_ID}"),), None,
    )
    assert TOKEN_ID not in record.getMessage()


def test_log_records_and_tracebacks_are_redacted(caplog):
    redact.install_log_redaction()
    logger = logging.getLogger("tests.redaction")

    with caplog.at_level(logging.INFO, logger="tests.redaction"):
        logger.info("calling modal with %s", TOKEN_ID)
        try:
            raise RuntimeError(f"auth failed for {TOKEN_SECRET}")
        except RuntimeError:
            logger.exception("deploy failed")

    text = caplog.text
    assert TOKEN_ID not in text and TOKEN_SECRET not in text
    assert redact.MASK in text and "deploy failed" in text


# --- import ---------------------------------------------------------------------------------


ENV = f"""
OTHER_SETTING=1
MODAL_ACCOUNT_1_NAME=main
MODAL_ACCOUNT_1_ID={TOKEN_ID}
MODAL_ACCOUNT_1_SECRET={TOKEN_SECRET}
MODAL_ACCOUNT_3_NAME=spare
MODAL_ACCOUNT_3_ID=ak-SecondAccount00001
MODAL_ACCOUNT_3_SECRET=as-SecondSecret0000000001
"""


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _accounts(env=ENV):
    from dotenv import dotenv_values

    return importer.accounts_from_env(dotenv_values(stream=io.StringIO(env)), "MODAL_ACCOUNT_")


def test_accounts_are_read_by_number_with_gaps():
    accounts = _accounts()
    assert [(a.slug, a.display_name) for a in accounts] == [("modal_1", "Modal 1 (main)"), ("modal_3", "Modal 3 (spare)")]


def test_an_account_missing_its_secret_is_refused():
    with pytest.raises(SystemExit, match="both MODAL_ACCOUNT_2_ID and MODAL_ACCOUNT_2_SECRET"):
        _accounts("MODAL_ACCOUNT_2_ID=ak-only00000000001\n")


def test_dry_run_writes_nothing(db, keys):
    rows = importer.plan_and_apply(db, _accounts(), keys[0], 30, apply=False)

    assert [r["action"] for r in rows] == ["create", "create"]
    assert db.query(Engine).count() == 0


def test_import_creates_paused_engines_with_sealed_credentials(db, keys):
    public, private = keys
    rows = importer.plan_and_apply(db, _accounts(), public, 30, apply=True)

    assert [r["token_id"] for r in rows] == ["…7890", "…0001"]  # never more than the last 4
    engine = db.query(Engine).filter_by(slug="modal_1").one()
    assert engine.status == "paused" and engine.adapter_type == "modal"
    assert engine.limit_usd == Decimal("30")
    assert engine.credentials_masked["token_secret"] == {"is_set": True, "hint": None}
    assert sealing.open_sealed(engine.credentials_sealed, [private], engine.id, engine.credentials_key_id) == {
        "token_id": TOKEN_ID, "token_secret": TOKEN_SECRET,
    }
    audits = db.query(AdminAudit).all()
    assert {a.action for a in audits} == {"engine.import.create"} and all(a.auth_method == "cli" for a in audits)
    assert TOKEN_SECRET not in str([a.after for a in audits]) and TOKEN_ID not in str([a.after for a in audits])


def test_import_is_idempotent_and_rotates_changed_credentials(db, keys):
    public, private = keys
    importer.plan_and_apply(db, _accounts(), public, 30, apply=True)

    assert [r["action"] for r in importer.plan_and_apply(db, _accounts(), public, 30, apply=True)] == [
        "unchanged", "unchanged",
    ]

    rotated = ENV.replace(TOKEN_SECRET, "as-RotatedSecret00000000009")
    assert importer.plan_and_apply(db, _accounts(rotated), public, None, apply=True)[0]["action"] == "update-credentials"
    engine = db.query(Engine).filter_by(slug="modal_1").one()
    assert sealing.open_sealed(engine.credentials_sealed, [private], engine.id, engine.credentials_key_id)[
        "token_secret"
    ] == "as-RotatedSecret00000000009"


def test_reimport_never_reactivates_an_engine(db, keys):
    importer.plan_and_apply(db, _accounts(), keys[0], 30, apply=True)
    engine = db.query(Engine).filter_by(slug="modal_1").one()
    engine.status = "active"
    db.commit()

    importer.plan_and_apply(db, _accounts(ENV.replace(TOKEN_SECRET, "as-Another0000000000000005")), keys[0], 30, apply=True)

    assert db.query(Engine).filter_by(slug="modal_1").one().status == "paused"
