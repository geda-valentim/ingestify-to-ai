"""The applied state a resource records once an operation is verified (spec 0007, 4.3 and 4.6)."""

MODE_AFTER = {"drain_stop": "stopped", "cooldown": "standby"}
OPT_IN_KEYS = ("opt_in_operation_id", "opt_in_actor")


def _opt_in(previous, profile, plan_body, operation_id, actor):
    """Who opted this applied revision in to the idle cooldown, if anyone.

    Set by the apply_profile of a revision with `idle_cooldown`; kept while the same
    revision stays applied (a cooldown, a start, a scale of it); dropped by any other
    application, so re-applying an old opted-in revision by another type does not
    revive it.
    """
    if plan_body["type"] == "apply_profile":
        if (profile.profile or {}).get("idle_cooldown"):
            return {"opt_in_operation_id": operation_id, "opt_in_actor": actor}
        return {}
    if (previous or {}).get("profile_id") != profile.id:
        return {}
    return {key: previous[key] for key in OPT_IN_KEYS if key in previous}


def applied_state(previous, profile, plan_body, operation_id, actor=None):
    """The resource's new `applied`: the profile, each feature's mode, who changed it last
    and, for an opted-in revision, the operation that opted it in.

    `operation_id` and `trigger` let the idle policy undo only its own cooldown;
    `opt_in_operation_id` lets opt_in() read the opt-in by primary key.
    """
    modes = dict((previous or {}).get("feature_modes") or {})
    modes[plan_body["feature"]] = MODE_AFTER.get(plan_body["type"], "running")
    return {
        "profile_id": profile.id,
        "revision": profile.revision,
        "type": plan_body["type"],
        "feature": profile.feature,
        "feature_modes": modes,
        "operation_id": operation_id,
        "trigger": plan_body.get("trigger"),
        **_opt_in(previous, profile, plan_body, operation_id, actor),
    }
