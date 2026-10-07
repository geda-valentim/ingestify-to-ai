"""Descriptors are shared by API/control runner; execution SDKs load lazily."""

from importlib import import_module

_registry = {}
_job_factories = {}
_capacity_validators = {}
_remote_factories = {"modal": "workers.engines.adapters.modal:ModalAdapter"}


def register(
    adapter_type,
    descriptor,
    factory=None,
    *,
    version=1,
    job_factory=None,
    capacity_validator=None,
    remote_factory=None,
):
    _registry[(adapter_type, version)] = (descriptor, factory)
    if remote_factory is not None:
        _remote_factories[adapter_type] = remote_factory
    if capacity_validator is not None:
        _capacity_validators[adapter_type] = capacity_validator
    if job_factory is not None:
        _job_factories[adapter_type] = job_factory


def remote_adapter(adapter_type, snapshot, credentials):
    factory = _remote_factories.get(adapter_type)
    if isinstance(factory, str):
        module, name = factory.rsplit(":", 1)
        factory = getattr(import_module(module), name)
    if factory is None:
        raise ValueError(f"No job adapter for {adapter_type}")
    return factory(snapshot, credentials)


def capacity_validator(adapter_type):
    return _capacity_validators.get(adapter_type)


def job_executor(adapter_type):
    factory = _job_factories.get(adapter_type)
    return factory() if factory else None


def execution_mode(adapter_type):
    try:
        return descriptor(adapter_type)["execution_mode"]
    except ValueError:
        return "queue" if adapter_type == "local" else "remote_runner"


def external_data(adapter_type):
    try:
        return descriptor(adapter_type).get("data_location") != "installation"
    except ValueError:
        return adapter_type != "local"


def descriptor(adapter_type, version=1):
    try:
        return _registry[(adapter_type, version)][0]
    except KeyError:
        raise ValueError(f"Unknown adapter/schema {adapter_type}@{version}") from None


def create(adapter_type, version=1):
    descriptor(adapter_type, version)
    d, factory = _registry[(adapter_type, version)]
    if isinstance(factory, str):
        module, name = factory.rsplit(":", 1)
        factory = getattr(import_module(module), name)
    if factory is None:
        raise ValueError("Adapter control executor is unavailable")
    return factory()


def descriptors():
    return [dict(d, adapter_version=v) for (t, v), (d, _) in _registry.items()]


def field(name, label, kind="number", **kwargs):
    return dict(name=name, label=label, type=kind, **kwargs)


COMMON = [
    field("desired_replicas", "Réplicas desejadas", min=0, max=100),
    field("max_replicas", "Máximo de réplicas", min=0, max=100),
    field("min_ready_replicas", "Réplicas aquecidas", min=0, max=100),
    field("idle_timeout_seconds", "Cooldown após ociosidade (s)", min=2, max=3600),
]
LOCAL = dict(
    type="local",
    title="Workers locais",
    schema_version=1,
    execution_mode="queue",
    create_connection=False,
    requires_budget=False,
    data_location="installation",
    scale_unit="worker",
    control_scope="compose_service",
    credential_fields=[],
    fields=COMMON,
    provider_fields=[field("host_id", "Host", "text")],
    features=["transcription", "document_conversion", "vision", "live-transcription"],
    actions=[
        "test",
        "start",
        "drain_stop",
        "restart",
        "scale",
        "warmup",
        "cooldown",
        "apply_profile",
    ],
    stop_destructive=False,
    dynamic_scale=True,
)
MODAL = dict(
    type="modal",
    title="Modal",
    schema_version=1,
    execution_mode="remote_runner",
    create_connection=True,
    requires_budget=True,
    requires_cleanup_watchdog=True,
    # Profiles bind only after "Testar" records the provider identity (TEST_CONNECTION_FIRST).
    requires_control_identity=True,
    data_location="provider",
    scale_unit="container",
    control_scope="deployment",
    credential_fields=[
        field("token_id", "Token ID", "secret", mask="last4"),
        field("token_secret", "Token secret", "secret", mask="none"),
    ],
    fields=COMMON,
    provider_fields=[],
    features=["transcription"],
    actions=[
        "test",
        "reconcile",
        "deploy",
        "start",
        "drain_stop",
        "restart",
        "scale",
        "warmup",
        "cooldown",
        "apply_profile",
    ],
    stop_destructive=True,
    dynamic_scale=True,
)
register("local", LOCAL, "workers.engine_control.local:LocalControlAdapter")
register("modal", MODAL, "workers.engine_control.modal:ModalControlAdapter")
