# GPU acceleration

**Short version: you do not need a GPU, and the default install will not download one's worth of drivers.**

A plain `pip install -r backend/requirements.txt` or a plain `docker compose up -d --build`
gives you a fully working stack on a laptop with integrated graphics, with **zero CUDA wheels**.
The obvious command is the correct one by construction — `requirements.txt` is a one-line alias
for the CPU set, so you cannot fall into the CUDA build by not having read this page.
Everything on this page is opt-in, and opting in takes two deliberate steps that are hard to do
by accident.

If you just cloned the repo and want it running, you can stop reading after
[Running CPU-only](#1-running-cpu-only-the-default).

---

## Contents

- [What actually uses a GPU](#what-actually-uses-a-gpu)
- [1. Running CPU-only (the default)](#1-running-cpu-only-the-default)
- [2. Host prerequisites for GPU](#2-host-prerequisites-for-gpu)
- [3. Enabling the GPU](#3-enabling-the-gpu)
- [4. Verifying the GPU is actually being used](#4-verifying-the-gpu-is-actually-being-used)
- [5. VRAM expectations](#5-vram-expectations)
- [6. Model weights: where they live, how to pre-download](#6-model-weights-where-they-live-how-to-pre-download)
- [7. Why the GPU reservation is not in the base compose file](#7-why-the-gpu-reservation-is-not-in-the-base-compose-file)
- [8. Troubleshooting](#8-troubleshooting)

---

## What actually uses a GPU

Three components in this stack can run on a GPU. They do **not** all benefit equally, and the
default configuration deliberately does not move all three at once.

| Component | What it does | Library | On GPU by default? |
|---|---|---|---|
| **Florence-2** | `POST /images/describe`, `POST /images/ocr` | transformers + torch | **Yes**, when you opt in — this is the whole point of the GPU path |
| **Whisper** | `POST /transcribe` | faster-whisper (CTranslate2) | Follows `DEVICE`, with a safety gate |
| **Docling** | PDF/DOCX → Markdown conversion | docling + torch | **Yes** in the GPU overlay — `worker` runs `DEVICE=cuda` as a single process |

Docling on the GPU is only safe because the overlay runs the `worker` service as **one process**
(`replicas: 1`, `--concurrency=1`). The base file runs `replicas: 5` at `--concurrency=2`: ten
processes, each with its own CUDA context and its own copy of the layout and table-recognition
weights — a near-certain out-of-memory on a consumer GPU, presenting as a generic
`Failed to convert document`. That is why the base file never asks for a GPU and the overlay
cuts the worker to one process before switching it to `cuda`.

Each process keeps one converter per option set (`workers/converter.py`, at most two resident),
so the weights load once per process rather than once per page. Measured on a 15-page edital
(RTX 5060 Ti): **5.6 s** per conversion on the GPU against ~50 s on CPU, identical Markdown,
**~0.9 GB** of VRAM. The first conversion in a process also pays ~15 s of model loading.

To scale documents, add replicas and budget ~1–1.5 GB of VRAM each against `nvidia-smi`;
never raise `--concurrency`.

### The one knob

There is a single device setting for the whole stack: **`DEVICE`**.

| Value | Meaning |
|---|---|
| `auto` *(default)* | Use CUDA if torch reports a usable device, otherwise CPU. Silent, one INFO log naming what was chosen. |
| `cpu` | Force CPU everywhere. |
| `cuda` | Force CUDA. If it cannot be satisfied the process **fails loudly**. |
| `cuda:N` | A specific GPU index on a multi-GPU host. |

The only difference between `auto` and `cuda` is what happens when CUDA is unavailable:
`auto` quietly falls back to CPU, `cuda` raises. That is why `cuda` is the right value when you
want to be *sure* the GPU is being used — a silent downgrade to CPU is the failure mode this
design exists to prevent.

`WHISPER_DEVICE` is a per-component override: leave it empty to inherit `DEVICE`, or set it to
`cpu`/`cuda` to pin audio transcription independently. See
[the migration note](#whisper_device-changed-meaning) before upgrading an existing `.env`.

---

## 1. Running CPU-only (the default)

### With Docker

```bash
cp .env.example .env
# Fill in the three required secrets:
#   JWT_SECRET_KEY   -> openssl rand -hex 32
#   MINIO_ROOT_USER  -> any username
#   MINIO_ROOT_PASSWORD -> openssl rand -hex 24
# Mirror MINIO_ROOT_* into MINIO_ACCESS_KEY / MINIO_SECRET_KEY.

docker compose up -d --build
```

That is the whole thing. `DEVICE` defaults to `auto`, torch comes from the PyTorch **CPU**
index, and no `nvidia-*` wheel is downloaded.

### Without Docker

```bash
python -m venv .venv && source .venv/bin/activate

# CPU, no vision — the default. requirements.txt is an alias of requirements-cpu.txt:
pip install -r backend/requirements.txt

# CPU, with Florence-2 image description and OCR:
pip install -r backend/requirements-vision.txt
```

> **`backend/requirements.txt` is safe to install.** It used to be the shared base that pinned
> no torch, which made the obvious command the wrong one; it is now a one-line alias for
> [`requirements-cpu.txt`](../backend/requirements-cpu.txt). The shared package list moved to
> [`requirements-base.txt`](../backend/requirements-base.txt) — **that** is the one you must not
> install directly.
>
> Why it matters: torch arrives transitively (`docling` → `docling-slim[standard]` →
> `torch>=2.2.2,<3.0.0`), and from plain PyPI that resolves to the **CUDA** build — roughly
> 1.66 GB of `nvidia-*` and `triton` wheels, about 3.4 GB installed, on a machine that may have
> no GPU at all. Measured with `pip install --dry-run --report` on a clean 3.12 venv:
> `requirements-base.txt` resolves 194 packages, `torch 2.13.0` (CUDA) and 16 `nvidia-*`/`triton`
> wheels **including `nvidia-cudnn-cu13`** — the exact cu13 tree that breaks CTranslate2 (see
> [§7](#7-troubleshooting)); `requirements.txt` resolves 175 packages, `torch 2.13.0+cpu` and
> zero `nvidia-*` wheels.
>
> How the `-cpu` / `-cuda` files force the right build: they configure a PyTorch index and pin
> `torch==2.13.0` at top level, so docling's transitive requirement can only resolve to that
> distribution. Note that pip does **not** rank indexes — candidates from `--index-url` and every
> `--extra-index-url` land in one flat namespace and the best *version* wins. What breaks the tie
> is PEP 440 local-version ordering: `2.13.0+cpu` sorts above `2.13.0`. The primary
> `--index-url` is still the right shape because the `+cpu` wheels exist only on the PyTorch
> index, and because making it primary keeps the CUDA-flavoured PyPI wheel out of the default
> search path instead of leaning on that tie-break. The reasoning is spelled out in
> [`requirements-cpu.txt`](../backend/requirements-cpu.txt).

### The dependency files

| File | Torch index | Vision extra | Use when |
|---|---|---|---|
| [`requirements.txt`](../backend/requirements.txt) | CPU | no | **The default.** One-line alias of `requirements-cpu.txt`. |
| [`requirements-cpu.txt`](../backend/requirements-cpu.txt) | CPU | no | Same set, named explicitly. API, beat, any CPU host. |
| [`requirements-vision.txt`](../backend/requirements-vision.txt) | CPU | yes | Default for the worker images. |
| [`requirements-cuda.txt`](../backend/requirements-cuda.txt) | cu129 | no | GPU host, no vision. |
| [`requirements-vision-cuda.txt`](../backend/requirements-vision-cuda.txt) | cu129 | yes | GPU host running Florence-2. |
| [`requirements-base.txt`](../backend/requirements-base.txt) | none | no | Shared package list. **Never install directly.** |

Expected sizes: CPU install lands site-packages around **2.6 GB** and the API image around
**3.2 GB**. The CUDA install adds roughly **2.5 GB** on top.

---

## 2. Host prerequisites for GPU

You need three things, in this order. Missing any one of them makes
`docker compose ... up` fail at container create, not degrade gracefully.

**a) An NVIDIA driver on the host.**

```bash
nvidia-smi
```

If that prints a table with your GPU and a driver version, you are done with this step. If the
command is not found, install your distribution's NVIDIA driver package first. The driver lives
on the *host* — never inside the container.

**b) The NVIDIA Container Toolkit.**

This is a separate package from the driver, and it is the one people miss. Follow the
[official install instructions](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
for your distro. On Debian/Ubuntu it is roughly:

```bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
```

**c) Register the runtime with Docker and restart the daemon.**

```bash
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

**Check all three at once:**

```bash
make gpu-check
```

or manually:

```bash
nvidia-smi -L                       # driver sees the GPU
command -v nvidia-ctk                # toolkit installed
docker info | grep -i runtime        # should list `nvidia` alongside `runc`
docker run --rm --gpus all nvidia/cuda:12.9.0-base-ubuntu24.04 nvidia-smi
```

That last command is the real test. If it prints your GPU, Docker can reach it and this repo
will too. If it says
`could not select device driver "nvidia" with capabilities: [[gpu]]`, step (b) or (c) is
incomplete.

---

## 3. Enabling the GPU

GPU is opt-in at **two independent levels**, and you need both.

### Level 1 — build time: which torch wheels get installed

Both Dockerfiles take two build args:

| Build arg | CPU default | CUDA value |
|---|---|---|
| `REQUIREMENTS_FILE` | `requirements-vision.txt` (worker) / `requirements-cpu.txt` (api) | `requirements-vision-cuda.txt` |
| `TORCH_INDEX_URL` | `https://download.pytorch.org/whl/cpu` | `https://download.pytorch.org/whl/cu129` |

[`docker-compose.gpu.yml`](../docker-compose.gpu.yml) sets both for the `worker-vision` service.
Nothing else in the stack is rebuilt against CUDA.

### Level 2 — runtime: device selection and the GPU reservation

The same overlay sets `DEVICE=cuda` on `worker-vision` and `worker` (Docling), cuts `worker` to
a single process, and runs `worker-audio` with `WHISPER_DEVICE=cuda`, each with a GPU
reservation.

### Do it

```bash
make gpu
```

which is exactly (plus `-f docker-compose.override.yml` when that file exists):

```bash
DOCKER_BUILDKIT=1 docker compose \
  -f docker-compose.yml \
  -f docker-compose.gpu.yml \
  up -d --build
```

### Make the GPU the default on a GPU host

`make gpu` is the only command that passes the overlay. Every other start path — a plain
`docker compose up`, `start.sh`, `rebuild.sh`, `make dev`, `make start` — loads only the base
file (and the override), **rebuilds the workers with CPU torch** and silently moves Docling and
Whisper off the GPU. On a host that has one, pin the file set in `.env`:

```bash
COMPOSE_FILE=docker-compose.yml:docker-compose.gpu.yml:docker-compose.override.yml
COMPOSE_PROFILES=infra   # only if redis/elasticsearch/minio run in this stack
```

Docker Compose reads both variables from `.env`, so every command above then brings up the GPU
stack. Leave them unset on machines without an NVIDIA GPU.

Production:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.gpu.yml up -d --build
```

> `DOCKER_BUILDKIT=1` matters: the pip cache mount in the Dockerfiles requires BuildKit.
> `make build`, `make gpu`, `start.sh` and `rebuild.sh` all set it.

### Choosing a different CUDA version

The default is **cu129**, and that is not arbitrary. cu13 torch builds pull the `nvidia-*-cu13`
wheels; **ctranslate2 4.x** — the engine behind faster-whisper — links the **cu12** cuDNN 9
layout and dies against a cu13 tree with the famously opaque
`Unable to load libcudnn_ops.so.9`. cu129 keeps torch on cu12 wheels and is still ≥ 12.8, so it
covers Blackwell (sm_120).

To target something else, override the build arg — do not edit the requirements file:

```yaml
# docker-compose.gpu.yml
build:
  args:
    TORCH_INDEX_URL: https://download.pytorch.org/whl/cu128
```

### Bare metal (no Docker)

```bash
pip install -r backend/requirements-vision-cuda.txt
export DEVICE=cuda
./run_worker.sh
```

---

## 4. Verifying the GPU is actually being used

The point of this section is that **"it didn't crash" is not evidence**. `DEVICE=auto` falls back
to CPU silently by design, so a stack that quietly runs everything on CPU looks identical to a
working GPU stack until you check.

### a) Ask the API

```bash
curl -s -H "X-API-Key: $YOUR_KEY" http://localhost:8000/images/capabilities | jq
```

```jsonc
{
  "enabled": true,
  "provider": "florence2",
  "model_id": "florence-community/Florence-2-base-ft",
  "revision": "0b03b6f1...",
  "device_requested": "cuda",
  "device_resolved": "cuda",       // <- this is the answer
  "torch_available": true,
  "cuda_available": true,
  "cuda_device_name": "NVIDIA GeForce RTX 5060 Ti",
  "dependencies_installed": true,
  "model_downloaded": true,
  "model_loaded": true,
  "trust_remote_code": false,
  "reason": null
}
```

`device_resolved` is computed **inside the worker process that actually loads the model**, not in
the API. That is deliberate: any other answer would be a guess about a different process.

If `device_requested` is `cuda` but `device_resolved` is `cpu`, `reason` says why.

### b) Read the worker log

```bash
make logs-vision
```

Every device decision is logged exactly once, at resolution time, naming both what was requested
and what was resolved:

```
INFO device=cuda (auto: NVIDIA GeForce RTX 5060 Ti)
INFO vision: loaded florence-community/Florence-2-base-ft@0b03b6f1 device=cuda dtype=float16 in 2841ms
```

A CPU fallback looks like this, and is never silent:

```
INFO device=cpu (auto: torch.cuda unavailable)
```

### c) Watch the GPU during a request

```bash
watch -n 0.5 nvidia-smi
```

Then send an image. You should see a `python` process appear with several hundred MB of memory
and non-zero utilisation. If memory is allocated but utilisation never moves, the model loaded on
the GPU but inference is happening elsewhere — check `VISION_TORCH_DTYPE`.

### d) The blunt instrument

Set `DEVICE=cuda` instead of `auto`. An explicit `cuda` that cannot be satisfied is a **hard
error** with an actionable message, never a fallback:

```
DEVICE=cuda was requested but torch reports no usable CUDA device (torch installed: yes).
Install the CUDA build (pip install -r backend/requirements-cuda.txt) or set DEVICE=auto.
```

If the stack comes up with `DEVICE=cuda`, the GPU is real.

---

## 5. VRAM expectations

Measured with the shipped defaults: Florence-2-base-ft in float16, Whisper `turbo` in float16.

| Component | Model | Weights | Peak during inference | Notes |
|---|---|---|---|---|
| Florence-2 | `Florence-2-base-ft` (0.23 B) | ~0.5 GB | **~1.0–1.5 GB** | `num_beams=3` and long OCR pages drive the peak |
| Florence-2 | `Florence-2-large-ft` (0.77 B) | ~1.6 GB | ~2.5–3.5 GB | Not the default; only worth it if quality matters more than latency |
| Whisper | `turbo` | ~1.6 GB | **~2.0–2.5 GB** | CTranslate2, float16 |
| Whisper | `base` | ~0.3 GB | ~0.5 GB | |
| Docling | layout + TableFormer | — | **~0.9 GB** | Measured, 15-page PDF, tables on, OCR off |
| CUDA context | — | — | ~0.3 GB **per process** | Unavoidable per-process overhead |

**Both together, default models, one process each: budget ~4 GB of VRAM.** An 8 GB card is
comfortable. A 6 GB card works if you drop Whisper to `small` or keep audio on CPU
(`WHISPER_DEVICE=cpu`). Below 6 GB, run vision on GPU and everything else on CPU.

Three things blow this budget, in descending order of likelihood:

1. **Raising `--concurrency` on `worker-vision`.** It is `1` on purpose: one resident model per
   box. Concurrency 2 means two full copies of the weights *and* two CUDA contexts. Scale with
   `docker compose up -d --scale worker-vision=N` if you have the VRAM, never with concurrency.
2. **Running Docling on the GPU in more than one process.** 10 worker processes × (CUDA
   context + layout/table weights) is several GB before a single page is converted. The GPU
   overlay runs `worker` as exactly one process on `DEVICE=cuda`; add replicas deliberately,
   never `--concurrency`.
3. **Whisper and Florence-2 landing in the same process.** They do not, in the shipped compose —
   audio runs on `worker-audio`, vision on `worker-vision`. Keep it that way.

Cheap knobs if you are tight on VRAM or latency:

- `VISION_NUM_BEAMS=1` — roughly **halves** latency, small quality cost. First thing to try.
- `VISION_MAX_NEW_TOKENS` — lowering it truncates long OCR pages; leave it at 1024 unless you
  only caption.
- `VISION_TORCH_DTYPE=float16` explicitly (this is what `auto` already picks on CUDA).
  Do **not** set `float16` on CPU: it is slow and numerically unstable for this model.

---

## 6. Model weights: where they live, how to pre-download

**Weights are never baked into an image.** They are downloaded on first use into a cache
directory that is backed by a named Docker volume.

| | |
|---|---|
| Path in container | `/models/huggingface` |
| Setting | `VISION_MODEL_CACHE_DIR` |
| Docker volume | `ingestify-hf-cache` |
| Mounted on | `worker` **and** `worker-vision` |
| Also set | `HF_HOME=/models/huggingface`, so incidental `huggingface_hub` calls land in the same place |
| Size | ~0.5 GB for `Florence-2-base-ft` |

The volume is shared between `worker` and `worker-vision` so that re-routing a task, or scaling
replicas, never triggers a second download.

### Pre-downloading

The first-ever request against an empty cache pays the download **plus** a 5–15 s model load,
inside the endpoint's 60 s budget — it will very likely return `504`. (The work is not lost: the
504 body carries `job_id` and `poll_url`, and the task keeps running because
`VISION_TASK_TIMEOUT_SECONDS` is deliberately double `VISION_REQUEST_TIMEOUT_SECONDS`. But it is
a bad first impression.)

Avoid it:

```bash
make vision-download
```

which runs `python -m workers.vision.download` inside `worker-vision` if it is up, and on the
host otherwise. Do this once after `docker compose up -d --build`, before your first request.

`worker-vision` also sets `VISION_PRELOAD_MODEL=true`, which loads the weights at worker-process
start, so once they are cached the first request pays nothing.

### Air-gapped / CI

```bash
VISION_ALLOW_MODEL_DOWNLOAD=false
```

This maps to `local_files_only=True` on every load. A missing cache then fails immediately with
`VISION_MODEL_NOT_DOWNLOADED` and an actionable message, instead of hanging on a network call
inside a request. Prefetch with `make vision-download` on a connected machine and ship the
`ingestify-hf-cache` volume.

### Clearing the cache

```bash
docker volume rm ingestify-hf-cache     # stack must be down
```

### A note on which model is pinned, and why

The default is `florence-community/Florence-2-base-ft` at a **commit sha**, never a branch.

The original `microsoft/Florence-2-*` repos are tagged `custom_code`: they ship
`modeling_florence2.py` and friends, and loading them requires `trust_remote_code=True`, which
downloads and **executes Python from the Hub inside the worker process** — with that process's
filesystem, network, MinIO credentials and `DATABASE_URL`. For an open-source project whose users
run `docker compose up` without reading it, that is an unacceptable default.

The `florence-community` conversions are weights-only (safetensors + configs, no `.py` files) and
load through the **native** `Florence2ForConditionalGeneration` in transformers ≥ 4.56. So the
shipped default executes no Hub-supplied code, and `VISION_TRUST_REMOTE_CODE` stays `false`.
Nothing in the code path ever flips it implicitly — in particular, a failed load never retries
with it enabled.

If you change `VISION_MODEL_ID`, you **must** also set a matching `VISION_MODEL_REVISION`. The
app refuses to start with a changed model id and the default model's sha, because that
combination is how a floating-branch pull sneaks in through a partial override. Look the sha up
at `https://huggingface.co/<model-id>/commits/main`.

---

## 7. Why the GPU reservation is not in the base compose file

Two independent reasons, both of which have bitten people:

**a) It is a start failure, not a graceful degrade.** On a host without
`nvidia-container-toolkit`, Compose hard-fails at container create with
`could not select device driver "nvidia" with capabilities: [[gpu]]`. There is no "try and fall
back". A GPU block in `docker-compose.yml` would mean a plain `docker compose up` is broken on
every machine without an NVIDIA GPU — the exact opposite of the open-source promise.

**b) You could not turn it off.** Compose merges
`deploy.resources.reservations.devices` by **replacing** the list, so a base-file GPU block
cannot be switched off by omission in an overlay. There would be no way back to CPU.

Hence: GPU lives only in [`docker-compose.gpu.yml`](../docker-compose.gpu.yml), and every new
variable in the base file uses the soft-default `${VAR:-default}` form. The hard
`${VAR:?message}` form is reserved for the three real secrets (`JWT_SECRET_KEY`,
`MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`). Nothing about GPU or vision may block
`docker compose up`.

---

## 8. Troubleshooting

### `could not select device driver "nvidia" with capabilities: [[gpu]]`

The container toolkit is missing or not registered with Docker.
Re-do [§2 (b) and (c)](#2-host-prerequisites-for-gpu) and confirm with
`docker run --rm --gpus all nvidia/cuda:12.9.0-base-ubuntu24.04 nvidia-smi`.

### `Unable to load libcudnn_ops.so.9` on transcription

CTranslate2 (faster-whisper) cannot find the cu12 cuDNN 9 layout. Either you built against a
cu13 index, or `nvidia-cudnn-cu12` is missing. Rebuild with the default
`TORCH_INDEX_URL=https://download.pytorch.org/whl/cu129`.

The stack guards against this: `resolve_whisper_device()` runs a real capability probe before
handing faster-whisper a CUDA device, and falls back to CPU with a logged `WARNING` naming the
reason rather than 500-ing every transcription. The probe is three checks — `import ctranslate2`,
then `ctranslate2.get_supported_compute_types("cuda")` (which initialises the CUDA backend and
enumerates what the device can actually compute), then a `ctypes.CDLL` of `libcudnn_ops.so.9`
itself. It deliberately does **not** use `get_cuda_device_count()`: that binds to
`cudaGetDeviceCount()` and only counts visible GPUs, so on any host with an NVIDIA driver it
returns ≥ 1 and would never fire. See
[spec 0002](specs/0002-dispositivo-unico-e-migracao-do-whisper.md). Look for:

```
WARNING audio: falling back to cpu - libcudnn_ops.so.9 cannot be loaded (...).
        Transcription would otherwise fail on every request. Install the CUDA
        build (pip install -r backend/requirements-cuda.txt), which pins the
        cu12 cuDNN 9 layout ctranslate2 needs; see docs/GPU.md.
```

### `CUDA out of memory`, or conversions failing with `Failed to convert document`

Almost always too many processes on one GPU. Check, in order: is `worker` pinned to
`DEVICE=cpu`? Is `worker-vision` still at `--concurrency=1`? Are you running more than one
`worker-vision` replica? See [§5](#5-vram-expectations).

### `pip install` still pulls `nvidia-*` wheels

You installed `backend/requirements-base.txt` directly, or an install path in your own tooling
still points at it. (Before the rename, `requirements.txt` *was* that base file — a stale script
carrying the old semantics is the usual cause.) Use `requirements.txt` / `requirements-cpu.txt` /
`requirements-vision.txt`. Verify with:

```bash
pip list 2>/dev/null | grep -E "^(torch|nvidia|triton)"
# CPU install should show torch 2.13.0+cpu and no nvidia-* rows
```

### The first `/images/describe` returns 504

Cold start: the model was not cached or not loaded. The work is still running — poll the
`poll_url` in the 504 body. Then run `make vision-download` so it does not happen again.

### `/images/capabilities` reports `"reason": "no vision worker heartbeat in the last 45s"`

`worker-vision` is down, or it is up but not consuming `ingestify-vision`. `docker compose ps`
and `make logs-vision`. This endpoint returns `200` with the bad news rather than `5xx` on
purpose — an ops probe must not fail just because the thing it probes is down.

**This means what it says, including while the worker is busy.** The answer comes from a
heartbeat each vision worker republishes to Redis every 15s from a background thread (TTL 45s),
*not* from a task queued on `ingestify-vision`. A queued probe used to sit behind an inference of
up to `VISION_TASK_TIMEOUT_SECONDS`, so the endpoint reported "no vision worker" whenever a
worker was there and working — and polling it piled probes onto the single vision slot, starving
the inference it was supposed to be diagnosing. So:

| what you see                                            | what it means                                   |
|---------------------------------------------------------|-------------------------------------------------|
| `dependencies_installed: true`                            | a vision worker is alive — busy or idle          |
| `dependencies_installed: false` + `no vision worker heartbeat` | nobody is consuming `ingestify-vision`     |
| `dependencies_installed: false` + `missing dependencies: …`    | the worker is alive without the vision extra |

Only a process actually started with `-Q ingestify-vision` publishes, so the five general
`worker` replicas cannot make this look healthy.

### `WHISPER_DEVICE` changed meaning

**This is a behaviour change on upgrade.** Previously, unset meant *CPU*. It now means
*inherit `DEVICE`*. On a GPU host, an existing `.env` that never set `WHISPER_DEVICE` will start
running Whisper on CUDA.

That is intended — CPU-Whisper beside GPU-Docling was the incoherence being fixed — but if you
want the old behaviour, say so explicitly:

```bash
WHISPER_DEVICE=cpu
```

A non-empty value always wins over `DEVICE`, and logs a `WARNING` on every boot so the override
is never invisible:

```
WARNING WHISPER_DEVICE=cpu overrides DEVICE=cuda for audio transcription only;
        unset it to follow DEVICE
```

That WARNING only reaches people who *set* the variable — i.e. exactly the people for whom
nothing changed. `WHISPER_DEVICE` did not exist before this change, so the affected population is
everyone who has it **unset**. They get their own line, once, the first time the audio device is
resolved:

```
WARNING audio: transcription now runs on cuda because WHISPER_DEVICE is unset and
        DEVICE=auto. This CHANGED: WHISPER_DEVICE used not to exist and audio was
        hardcoded to cpu. Set WHISPER_DEVICE=cpu to keep the old behaviour.
```

You will see at most one of the two. Full rationale in
[spec 0002](specs/0002-dispositivo-unico-e-migracao-do-whisper.md).

`WHISPER_COMPUTE_TYPE` changed the same way: empty now derives `float16` on CUDA and `int8` on
CPU, which closes the trap where flipping only the device leaves CTranslate2 on a CPU-shaped
`int8` quantisation that it silently downgrades rather than rejects.

### `DOCLING_DEVICE` appears to do nothing

It is ignored from now on. The device is passed explicitly into
`AcceleratorOptions(device=...)` from `DEVICE`, and a pydantic-settings init kwarg outranks the
environment. Use `DEVICE` (and `DOCLING_NUM_THREADS` for CPU thread count).

---

## See also

- [`.env.example`](../.env.example) — every variable, with how to choose a value
- [`docker-compose.gpu.yml`](../docker-compose.gpu.yml) — the entire GPU declaration
- [`backend/requirements-cuda.txt`](../backend/requirements-cuda.txt) — why cu129
- [`docs/DOCKER_OPTIMIZATION.md`](DOCKER_OPTIMIZATION.md) — image size and build tuning
