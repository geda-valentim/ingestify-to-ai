# Python dependency review — 2026-10-06

The default application sets now resolve patched web, document, image and JWT
libraries. WhisperX and Diart remain blocked in production because the available
upstream releases cannot supply a patched, qualified dependency set. Their audit
findings are retained; the release gate does not make those packages safe.

## Changes and validation

FastAPI 0.142.2 / Starlette 1.7.0, multipart 0.0.32, AnyIO 4.15.1 and dotenv 1.2.4
replace vulnerable request/form parsers and configuration loading. Unauthenticated
login forms and upload endpoints make the parser denial-of-service findings
relevant before endpoint authentication/rate limiting runs. Starlette's
[urlencoded form limits advisory](https://github.com/Kludex/starlette/security/advisories/GHSA-82w8-qh3p-5jfq)
explains why endpoint budgets alone were insufficient.

Docling has a security floor of 2.118.1 and resolved to 2.133.0. This includes
fixes for archive/XML/path handling and the
[HTML local-file rendering disclosure](https://github.com/docling-project/docling/security/advisories/GHSA-q43m-vhcp-mhvm).
The latter requires explicitly enabled HTML browser rendering; the default PDF
pipeline does not enable it. Upgrading also closes vulnerabilities in other
formats as the converter's supported input surface evolves. Real imports and
CPU converter configuration passed offline without loading/downloading models.

The obsolete PyPDF2 package was replaced by maintained pypdf 6.19.0 and PdfWriter
merging. A real two-page merge verifies the output pages and bookmark target.
PyJWT 2.15.1 replaces python-jose/ecdsa; HS256 is the only configurable algorithm.
An independently constructed legacy HS256 token still verifies, while unsigned
and non-string-subject tokens fail. The removed ECDSA timing vulnerability was
not reachable through the application's HS256 authentication, but retaining an
unneeded, unpatched crypto implementation was unnecessary.

Vision sets now require Pillow >=12.3 and Transformers >=5.10. The former parses
uploaded image bytes, so native decoder vulnerabilities are relevant even with
byte/pixel caps. Real Pillow pixel-bomb guard tests pass. Dropbox 12.2.2 replaces
11.36.2, whose import failed after setuptools removed pkg_resources; the real SDK
and workers.sources imports pass with the current setuptools.

Docling requires websockets <17; version 16.0 is compatible and audited. Existing
live/remote/WebSocket and Whisper-core contract tests pass with that version.
The three application WhisperX locks were regenerated for patched dotenv and
live FastAPI/Starlette/Uvicorn, preserving the constrained model-runtime pins.

`backend/requirements-test.in` and its hashed `requirements-test.lock` provide
reproducible lightweight tests without torch, Docling, browser binaries or model
weights. They include real Pillow, numpy and fakeredis Lua support. Install in a
fresh Python 3.11 or 3.13 environment with `uv pip install --require-hashes --no-deps -r
backend/requirements-test.lock`; run `python -m pytest backend/tests`. The lock is
universal and includes `audioop-lts` only on Python >=3.13, where stdlib audioop
was removed. Real API, source SDK, pydub PCM and faster-whisper feature-extractor
imports were validated on Python 3.13 without model downloads.
See [audioop-lts](https://pypi.org/project/audioop-lts/) for the compatibility port.

## Audit coverage

Resolved sets were scanned with pip-audit, including transitive packages, without
installing GPU wheels or downloading models. No packages were skipped. CPU local
wheel versions are normalized to their public versions for advisory matching;
Diart's direct torch/torchaudio/torchvision URLs are parsed as pinned wheels.

| Dependency set | Result |
| --- | --- |
| Default CPU, CUDA | No known advisories in the audited resolution |
| Vision CPU, CUDA | No known advisories in the audited resolution |
| Default live CUDA | No known advisories in the audited resolution |
| worker-remote, Modal faster-whisper lock | No known advisories in the audited resolution |
| WhisperX CPU/CUDA, application CPU/CUDA, live WhisperX | Unresolved torch, Transformers and NLTK findings; production blocked |
| Diart CPU/CUDA | Unresolved torch findings; production blocked |

These are dated audit results, not a guarantee against future advisories. Raw
resolved requirements, normalized lock inputs and JSON reports are retained in
`/tmp/ingestify-security-audit` for this review. CI must continue scanning the
blocked optional sets and report their findings rather than globally ignoring
those advisory IDs.

## Unresolved ML findings and enforced release gate

[WhisperX's current 3.8.6 metadata](https://pypi.org/pypi/whisperx/3.8.6/json)
requires torch ~=2.8.0 and huggingface-hub <1.0. Patched Transformers 5.10 requires
huggingface-hub >=1.5, and patched torch loaders require >=2.10. Thus a compatible
upgrade is not available without changing/forking upstream runtime requirements
and requalifying the inference stack. Diart 0.9.2 remains paired with the older
Pyannote/SpeechBrain/torchaudio stack; a blind torch upgrade is not qualification.

The most consequential remaining torch finding is
[malicious checkpoints corrupting the weights-only unpickler](https://github.com/pytorch/pytorch/security/advisories/GHSA-63cw-57p8-fm3p).
`weights_only=True` and safe_globals do not neutralize this vulnerability.
Other torch findings involve tensor operators, TorchScript and PT2 loading.
Transformers findings include malicious model-config code execution and tokenizer
path writes. The application does not expose model upload, trainer, checkpoint
conversion or arbitrary model-path APIs, but compromised provisioning/model
artifacts would still be dangerous in these runtimes.

[NLTK's remaining model-path sandbox bypass](https://github.com/nltk/nltk/security/advisories/GHSA-8mgp-746c-j5xp)
requires caller-controlled model import/export paths. No application endpoint
invokes those NLTK model-artifact APIs; users submit audio, not NLTK model paths.
Offline provisioning, revision/path checks and read-only model mounts reduce
artifact substitution, but do not repair dependency vulnerabilities.

Production Settings reject WhisperX configuration and enabled live diarization.
The audio factory also rejects a forced WhisperX provider before cache lookup or
model construction, covering persisted profiles, retries and job options while
the default provider is faster-whisper. Independent guards run before
WhisperXRuntime construction/loading/transcription and Diart subprocess/session
initialization. Missing ENVIRONMENT defaults to production; only explicit
ENVIRONMENT=development permits local qualification. No production bypass flag
exists. Modal images explicitly set production, and the remote runner enforces
the gate even if invoked from a development deployment process or given an
already constructed model/custom inference function.

The release-gate tests cover configuration, forced-provider/profile-style
options, cached models, direct runtime constructors, Diart and remote execution.
Unblocking requires patched upstream constraints (or a reviewed maintained
fork), clean complete audits, CPU/GPU import checks and the existing offline
model/inference qualification gates. Merely changing the audit allowlist,
manifest's `qualified` boolean or ENVIRONMENT on a production installation is
not an approved remediation.
