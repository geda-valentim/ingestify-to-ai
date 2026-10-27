"""Compose services the engine host agent may operate, and the profile each one sits behind."""

SERVICES = {
    "worker",
    "worker-audio",
    "worker-vision",
    "worker-live",
    "worker-dispatch",
    "worker-remote",
}

# Services behind a Compose profile. Passed explicitly on every call that names one:
# an older Compose may not activate a named service's profile and `ps` then comes back
# empty without an error, which reads as "no replicas".
SERVICE_PROFILES = {"worker-live": "live", "worker-dispatch": "engines", "worker-remote": "engines"}


def profile_args(service):
    """`--profile <name>` for a service behind a profile, nothing otherwise."""
    profile = SERVICE_PROFILES.get(service)
    return ["--profile", profile] if profile else []
