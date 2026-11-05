"""Code moved by domain keeps working through its old import path (callers unchanged)."""


def test_operation_events_stay_reachable_from_the_service():
    from shared.engine_control import operation_events, service

    assert service.events is operation_events.events


def test_access_audit_stays_reachable_from_the_policy():
    from shared.access import audit, policy

    assert policy.audit is audit.audit


def test_operation_views_stay_reachable_from_the_routes():
    from api import engine_control_routes, engine_operation_views

    assert engine_control_routes.operation_view is engine_operation_views.operation_view
    assert engine_control_routes.can_read_operation is engine_operation_views.can_read_operation


def test_the_api_registers_the_force_cancel_holder_probe():
    import api.engine_control_routes  # noqa: F401
    from api.force_cancel_probe import holder_verdicts
    from shared.engine_control import force_cancel

    assert force_cancel._probe is holder_verdicts
