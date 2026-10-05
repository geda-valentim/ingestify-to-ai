"""
The Modal side of spec 0003: what is deployed to a Modal account and how the
worker talks to it.

    protocol.py      request/response of one transcription, with limits (no deps)
    runner.py        what the container does with a request (no modal, no shared)
    fingerprint.py   hash of everything a deploy contains, binding included
    image.py         the container image recipe (imports modal)
    whisper_app.py   the deploy target (imports modal)

Only worker-remote and the deploy CLI import the last two; nothing here is
imported by the API, the local workers or the dispatcher at module load.
"""
