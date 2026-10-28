"""
Spec 0007, 4.3 and 4.6: what a resource records once an operation is verified. Besides
the profile and each feature's mode, who changed it last (`operation_id`, `trigger`) and,
for a revision opted in to the idle cooldown, the apply_profile that opted it in.
"""

from types import SimpleNamespace

from shared.engine_control.applied_state import OPT_IN_KEYS, applied_state

ON = SimpleNamespace(id=10, revision=1, feature="transcription", profile={"idle_cooldown": True})
OFF = SimpleNamespace(id=11, revision=2, feature="transcription", profile={"idle_cooldown": False})


def _body(type_, trigger=None):
    return {"type": type_, "feature": "transcription", **({"trigger": trigger} if trigger else {})}


def _opt_in(state):
    return {key: state[key] for key in OPT_IN_KEYS if key in state}


def test_it_records_the_operation_and_its_trigger():
    state = applied_state(None, ON, _body("cooldown", "idle_policy"), "op-1", "admin-a")

    assert state["operation_id"] == "op-1" and state["trigger"] == "idle_policy"
    assert state["feature_modes"] == {"transcription": "standby"}


def test_the_apply_profile_of_an_opted_in_revision_records_the_opt_in():
    state = applied_state(None, ON, _body("apply_profile"), "op-1", "admin-a")

    assert _opt_in(state) == {"opt_in_operation_id": "op-1", "opt_in_actor": "admin-a"}


def test_a_revision_without_the_opt_in_records_none():
    assert _opt_in(applied_state(None, OFF, _body("apply_profile"), "op-1", "admin-a")) == {}


def test_operations_on_the_same_revision_keep_it():
    opted = applied_state(None, ON, _body("apply_profile"), "op-1", "admin-a")
    for type_, trigger in (("cooldown", "idle_policy"), ("start", "wakeup"), ("drain_stop", None)):
        opted = applied_state(opted, ON, _body(type_, trigger), f"op-{type_}", "someone-else")

    assert _opt_in(opted) == {"opt_in_operation_id": "op-1", "opt_in_actor": "admin-a"}


def test_another_revision_drops_it_and_reapplying_the_old_one_by_another_type_does_not_revive_it():
    opted = applied_state(None, ON, _body("apply_profile"), "op-1", "admin-a")
    other = applied_state(opted, OFF, _body("apply_profile"), "op-2", "admin-a")
    back = applied_state(other, ON, _body("start"), "op-3", "operator-b")

    assert _opt_in(other) == {} and _opt_in(back) == {}


def test_a_new_apply_profile_of_the_same_revision_takes_it_over():
    opted = applied_state(None, ON, _body("apply_profile"), "op-1", "admin-a")
    again = applied_state(opted, ON, _body("apply_profile"), "op-2", "admin-b")

    assert _opt_in(again) == {"opt_in_operation_id": "op-2", "opt_in_actor": "admin-b"}


def test_a_shared_row_never_lends_another_profile_s_opt_in():
    """The GPU and generic rows are written by vision and transcription alike."""
    vision = SimpleNamespace(id=20, revision=1, feature="vision", profile={"idle_cooldown": True})
    opted = applied_state(None, vision, {"type": "apply_profile", "feature": "vision"}, "op-v", "admin-v")

    assert _opt_in(applied_state(opted, ON, _body("start"), "op-t", "operator-b")) == {}
