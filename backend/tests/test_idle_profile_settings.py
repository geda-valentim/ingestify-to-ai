"""Execution profiles and the idle cooldown field (spec 0007 §4.6): revisions published before
the field existed still bind, and an execution profile cannot opt in off a local engine."""
import pytest

from shared.access import contracts as C, service
from shared.access.models import ExecutionRevision
from shared.engine_control import service as control
from shared.engine_control.models import RuntimeProfile
from shared.models import Engine
from tests.test_execution_profiles import draft, published, settings
from tests.test_execution_profiles import world  # noqa: F401  (fixture)


def test_a_revision_published_before_a_runtime_field_existed_still_binds(world):
    # idle_cooldown (spec 0007 §4.6) was added to RuntimeSettings after revisions were published;
    # the stored settings lack the key, the freshly validated ones carry its default
    with world() as db:
        p = published(db)
        rev = db.get(ExecutionRevision, p["latest_published_revision_id"])
        rev.settings = {k: v for k, v in rev.settings.items() if k != "idle_cooldown"}
        db.commit()
        service.bind(
            db,
            db.get(Engine, "engine-a"),
            C.Bind(version=0, feature="transcription", revision_id=rev.id),
            "bootstrap",
        )
        bound = db.query(RuntimeProfile).filter_by(engine_id="engine-a", feature="transcription").one()
        assert bound.profile["idle_cooldown"] is False


def test_an_execution_profile_cannot_opt_in_to_idle_cooldown_off_local(world):
    # refused on save, not only when an engine binds it later
    with world() as db:
        with pytest.raises(control.ControlError) as e:
            draft(db, settings=dict(settings(), idle_cooldown=True))
        assert e.value.code == "IDLE_COOLDOWN_NOT_SUPPORTED"


def test_moved_code_stays_reachable_from_its_old_path():
    from shared.access import profile_views

    assert service.revision_view is profile_views.revision_view
