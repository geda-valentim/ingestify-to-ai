"""
Live captions of remote transcriptions (spec 0003, slice 7), against a fake `modal`:
the container pushes decoded segments in batches to its attempt's partition of the
account's live Queue (protocol 3, bounded, best effort); worker-remote drains it
between short waits and appends the validated segments to the same Redis list the
local path writes (job:{id}:transcript:partial), so GET /jobs/{id}/transcript/partial
and the job page's live view work for remote jobs too. A new attempt starts from an
empty list; a resumed worker drains only what is left. Nothing touches the network.
"""

import pytest

from tests._fake_modal import Clock, FakeModal, response_for
from tests.test_modal_adapter import TOKEN_ID, adapter, context
from tests.test_remote_engine import TOKEN_ID as REMOTE_TOKEN_ID
from tests.test_remote_engine import place_remote, run, world  # noqa: F401  (fixture)
from workers.engines.modal_apps import protocol, runner


class FakeQueue:
    def __init__(self, fail=False):
        self.items = {}
        self.fail = fail
        self.puts = []

    def put(self, value, block=True, timeout=None, *, partition=None, partition_ttl=86400):
        self.puts.append((partition, partition_ttl, block))
        if self.fail:
            raise RuntimeError("queue.Full")
        self.items.setdefault(partition, []).append(value)


def segmented(n, step=1.0):
    """A transcribe() stand-in that decodes n segments, reporting each through on_progress"""
    def transcribe(model, path, options, *, model_name, should_cancel, on_progress=None):
        segments = []
        if on_progress:
            on_progress(0.0, n * step)
        for i in range(n):
            segment = {"start": i * step, "end": (i + 1) * step, "text": f"s{i}"}
            segments.append(segment)
            if on_progress:
                on_progress(segment["end"], n * step, segment=segment)
        return {"text": " ".join(s["text"] for s in segments), "segments": segments, "language": "pt",
                "language_probability": 0.9, "duration": n * step, "word_count": n, "char_count": 3 * n,
                "model": model_name, "provider": "faster-whisper"}
    return transcribe


def handle(request, queue, transcribe, clock):
    return runner.handle(request, model=None, state=None, container_id="c", call_id=None, cold_start_seconds=0,
                         gpu="L4", fingerprint="f", transcribe=transcribe, clock=clock, live=queue)


# --- the wire ------------------------------------------------------------------------------------


def test_protocol_3_carries_the_live_flag_and_validates_batches():
    assert protocol.PROTOCOL_VERSION == 3
    request = protocol.build_request(attempt_key="k", media=b"m", suffix=".mp3", options={}, deadline_unix=1e9,
                                     live=True)
    assert protocol.parse_request(request)["live"] is True
    assert protocol.parse_request({k: v for k, v in request.items() if k != "live"})["live"] is False
    with pytest.raises(protocol.ProtocolError):
        protocol.parse_request({**request, "live": "yes"})

    batch = protocol.live_batch([{"start": 0, "end": 1.5, "text": "olá"}])
    assert protocol.parse_live_batch(batch) == [{"start": 0.0, "end": 1.5, "text": "olá"}]
    for bad in ({"protocol": 2, "segments": []}, {"protocol": 3, "segments": "x"},
                {"protocol": 3, "segments": [{"start": "0", "end": 1, "text": "a"}]},
                {"protocol": 3, "segments": [{"start": 0, "end": 1, "text": "a" * 20_001}]},
                {"protocol": 3, "segments": [{"start": 0, "end": 1}] * (protocol.LIVE_MAX_SEGMENTS_PER_BATCH + 1)}):
        with pytest.raises(protocol.ProtocolError):
            protocol.parse_live_batch(bad)


# --- the container -------------------------------------------------------------------------------


def test_the_container_pushes_batches_to_its_attempts_partition():
    queue = FakeQueue()
    request = protocol.build_request(attempt_key="attempt-9", media=b"m", suffix=".mp3", options={},
                                     deadline_unix=1e10, live=True)
    raw = handle(request, queue, segmented(10), Clock(start=0.0, step=0.5))
    result, _ = protocol.parse_response(raw)
    batches = queue.items["attempt-9"]
    pushed = [s for b in batches for s in protocol.parse_live_batch(b)]
    assert [s["text"] for s in pushed] == [s["text"] for s in result["segments"]]  # every segment, in order
    assert 1 < len(batches) < 10  # batched by time, not one put per segment
    assert all(p == ("attempt-9", protocol.LIVE_PARTITION_TTL_SECONDS, False) for p in queue.puts)  # never blocks


def test_without_live_or_without_a_queue_nothing_is_pushed():
    queue = FakeQueue()
    request = protocol.build_request(attempt_key="k", media=b"m", suffix=".mp3", options={}, deadline_unix=1e10)
    handle(request, queue, segmented(5), Clock(start=0.0, step=1.0))
    assert queue.puts == []
    live = protocol.build_request(attempt_key="k2", media=b"m", suffix=".mp3", options={}, deadline_unix=1e10,
                                  live=True)
    handle(live, None, segmented(5), Clock(start=0.0, step=1.0))  # an old deploy's container: no queue


def test_live_text_is_bounded_and_never_fails_the_transcription(monkeypatch):
    monkeypatch.setattr(protocol, "LIVE_MAX_BATCHES", 2)
    queue = FakeQueue()
    request = protocol.build_request(attempt_key="k", media=b"m", suffix=".mp3", options={}, deadline_unix=1e10,
                                     live=True)
    raw = handle(request, queue, segmented(40), Clock(start=0.0, step=3.0))
    assert len(queue.items["k"]) == 2 and len(protocol.parse_response(raw)[0]["segments"]) == 40

    broken = FakeQueue(fail=True)
    raw = handle(request, broken, segmented(20), Clock(start=0.0, step=3.0))
    assert len(broken.puts) == 1  # the first failure stops pushing; the result is intact
    assert len(protocol.parse_response(raw)[0]["segments"]) == 20


# --- the adapter: drained between short waits --------------------------------------------------


def test_the_adapter_drains_validated_segments_while_it_waits_and_keeps_the_heartbeat_cadence():
    clock = Clock(start=1_000.0)
    a, fake = adapter(clock=clock)
    account = fake.account(TOKEN_ID)
    account.clock = clock
    account.behaviour = lambda request: (10, response_for(request))
    polls = {"n": 0}

    def push(call):
        polls["n"] += 1
        partition = protocol.live_partition("attempt-1")
        account.queues.setdefault(partition, []).append(
            protocol.live_batch([{"start": polls["n"], "end": polls["n"] + 1, "text": f"p{polls['n']}"}]))
        if polls["n"] == 3:
            account.queues[partition].append({"protocol": 3, "segments": "garbage"})  # dropped, not raised

    account.on_poll = push
    received = []
    ctx, calls = context(on_segments=received.extend)
    a.execute(media=b"ID3", suffix=".mp3", options={}, ctx=ctx, budget_seconds=3_600)

    assert account.spawned[0]["live"] is True
    assert [s["text"] for s in received] == [f"p{i}" for i in range(1, 11)]
    assert all(t == 3.0 for t in account.calls["fc-1"].gets[:-1])  # 3 s slices with live captions
    assert calls["beats"] == 2  # 30 s of waiting: the 15 s heartbeat cadence is unchanged
    assert account.cleared == [protocol.live_partition("attempt-1")]


def test_without_live_captions_the_adapter_waits_as_before():
    clock = Clock(start=1_000.0)
    a, fake = adapter(clock=clock)
    account = fake.account(TOKEN_ID)
    account.clock = clock
    account.behaviour = lambda request: (2, response_for(request))
    ctx, calls = context()
    a.execute(media=b"ID3", suffix=".mp3", options={}, ctx=ctx, budget_seconds=300)
    assert account.spawned[0]["live"] is False
    assert account.calls["fc-1"].gets[:2] == [15.0, 15.0] and calls["beats"] == 2 and account.cleared == []


def test_an_unreadable_live_queue_never_fails_the_call():
    clock = Clock(start=1_000.0)
    a, fake = adapter(clock=clock)
    account = fake.account(TOKEN_ID)
    account.clock = clock
    account.behaviour = lambda request: (3, response_for(request))
    account.queue_error = RuntimeError("queue service unavailable")
    ctx, _ = context(on_segments=lambda segments: pytest.fail("nothing to deliver"))
    assert a.execute(media=b"ID3", suffix=".mp3", options={}, ctx=ctx, budget_seconds=300).output["text"]


# --- worker-remote end to end: the job page's live list ------------------------------------------


def test_a_remote_job_fills_the_same_live_list_as_a_local_one(world):  # noqa: F811
    item, usage_id = place_remote(world)
    job_id = world.item(item).job_id
    world.redis.append_partial_transcript(job_id, [{"start": 0, "end": 1, "text": "from an older attempt"}])
    account = world.fake.account(REMOTE_TOKEN_ID)
    account.behaviour = lambda request: (4, response_for(request))
    seen = []

    def push(call):
        key = account.spawned[-1]["attempt_key"]
        n = len(account.calls) and len(call.gets)
        account.queues.setdefault(protocol.live_partition(key), []).append(
            protocol.live_batch([{"start": n, "end": n + 1, "text": f"live {n}"}]))
        seen.append(world.redis.get_partial_transcript(job_id)[0])

    account.on_poll = push
    assert run(world, usage_id) == "succeeded"
    # While the call ran, the list held this attempt's segments only, growing poll by poll
    assert [s["text"] for s in seen[-1]] == ["live 1", "live 2", "live 3"]
    assert all("older attempt" not in str(snapshot) for snapshot in seen)
    # finish_transcription (stubbed here) owns the cleanup once the full result exists


def test_a_resumed_attempt_keeps_the_live_text_and_drains_only_what_is_left(world):  # noqa: F811
    from datetime import datetime, timedelta

    from shared.models import EngineUsage

    item, usage_id = place_remote(world)
    job_id = world.item(item).job_id
    account = world.fake.account(REMOTE_TOKEN_ID)
    account.behaviour = lambda request: (None, None)

    # First worker: spawned and recorded the call, drained one batch, then died
    def first_poll(call):
        key = account.spawned[-1]["attempt_key"]
        account.queues.setdefault(protocol.live_partition(key), []).append(
            protocol.live_batch([{"start": 0, "end": 1, "text": "before the crash"}]))
        account.on_poll = None
        raise SystemExit  # the thread dies mid-wait

    account.on_poll = first_poll
    with pytest.raises(SystemExit):
        run(world, usage_id)
    key = account.spawned[-1]["attempt_key"]
    assert world.redis.get_partial_transcript(job_id)[0] == []  # the batch never reached Redis
    with world.Session() as db:
        row = db.get(EngineUsage, usage_id)
        row.heartbeat_at = row.heartbeat_at - timedelta(minutes=5)
        row.deadline_at = datetime.utcnow() + timedelta(minutes=30)  # the fake clock lives in 1970
        db.commit()

    # Second worker resumes the recorded call: the partition still has the batch; no reset
    world.redis.append_partial_transcript(job_id, [{"start": -1, "end": 0, "text": "kept"}])
    account.calls["fc-1"].polls_left = 1
    account.calls["fc-1"].outcome = response_for(account.spawned[-1])
    assert run(world, usage_id) == "succeeded"
    assert len(account.spawned) == 1  # resumed, not spawned again
    texts = [s["text"] for s in world.redis.get_partial_transcript(job_id)[0]]
    assert texts == ["kept", "before the crash"]
    assert account.queues.get(protocol.live_partition(key)) in (None, [])
