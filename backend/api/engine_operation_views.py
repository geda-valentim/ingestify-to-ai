"""An engine operation as a given user may see and act on it (spec 0007)."""

from shared.engine_control import service


def can_read_operation(db, op, actor):
    try:
        service.authorize_operation(db, op.id, actor)
        return True
    except service.ControlError:
        return False


def operation_view(db, op, actor):
    out = service.operation_view(op)
    for flag, permission in [
        ("can_cancel", "engine_operations.cancel"),
        ("can_recover", "engine_operations.recover"),
    ]:
        try:
            service.authorize_operation(db, op.id, actor, permission)
        except service.ControlError:
            out[flag] = False
    return out
