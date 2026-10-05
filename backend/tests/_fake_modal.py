"""
A fake `modal` module for the remote engine tests (spec 0003, slice 4a): the
surface ModalAdapter uses (Client.from_credentials, Cls/Function/Dict.from_name
with client=, FunctionCall.from_id/get/cancel, the exception classes), per
account and without any network. Each account has its own state Dict, deploy
flag and calls; a call's behaviour is scripted by `account.behaviour(request)`.
"""

from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional

from workers.engines.modal_apps import protocol


class _Exc:
    class Error(Exception):
        pass

    class AuthError(Error):
        pass

    class NotFoundError(Error):
        pass

    class ResourceExhaustedError(Error):
        pass

    class FunctionTimeoutError(Error):
        pass

    class OutputExpiredError(Error):
        pass

    class ConflictError(Error):
        pass


def response_for(request, *, exec_seconds=100.0, cold=12.0, container="ta-container-1", started=None, text="olá mundo"):
    started = started if started is not None else 1_000.0
    result = {
        "text": text, "segments": [{"start": 0.0, "end": 2.0, "text": text}], "language": "pt",
        "language_probability": 0.98, "duration": 600.0, "word_count": len(text.split()), "char_count": len(text),
        "model": "turbo", "provider": "faster-whisper",
    }
    usage = {"exec_started_unix": started, "exec_ended_unix": started + exec_seconds, "exec_seconds": exec_seconds,
             "cold_start_seconds": cold, "container_id": container, "gpu": "L4", "model": "turbo",
             "compute_type": "float16", "fingerprint": "f" * 64, "protocol": protocol.PROTOCOL_VERSION}
    return protocol.build_response(result, usage)


class Account:
    def __init__(self, token_id: str):
        self.token_id = token_id
        self.state: Dict[Any, Any] = {}
        self.deployed = True
        self.calls: Dict[str, "FakeCall"] = {}
        self.spawned: List[dict] = []
        self.auth_error: Optional[str] = None
        self.spawn_error: Optional[Exception] = None
        # request -> (polls before the result, result or exception); None = never finishes
        self.behaviour: Callable[[dict], Any] = lambda request: (1, response_for(request))
        self.meta = None
        self.clock: Optional["Clock"] = None  # waiting on a call moves it forward by the timeout
        self.queues: Dict[str, List[Any]] = {}  # the live Queue, by partition (protocol 3)
        self.cleared: List[str] = []
        self.queue_error: Optional[Exception] = None
        # call -> None, run on every wait that times out: lets a test push live batches mid-call
        self.on_poll: Optional[Callable[["FakeCall"], None]] = None


class FakeCall:
    def __init__(self, account: Account, call_id: str, polls: Optional[int], outcome):
        self.account = account
        self.object_id = call_id
        self.polls_left = polls
        self.outcome = outcome
        self.cancelled = False
        self.gets: List[float] = []

    def get(self, timeout=None):
        self.gets.append(timeout)
        if self.cancelled:
            raise _Exc.Error("the call was cancelled")
        if self.polls_left is None or self.polls_left > 0:
            if self.polls_left:
                self.polls_left -= 1
            if self.account.clock is not None:
                self.account.clock.now += timeout or 0
            if self.account.on_poll is not None:
                self.account.on_poll(self)
            raise TimeoutError()
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome

    def cancel(self, terminate_containers=False):
        self.cancelled = True


class FakeModal:
    """Stands in for the `modal` package; `accounts` is keyed by token id"""

    def __init__(self):
        self.accounts: Dict[str, Account] = {}
        self.clients: List[tuple] = []
        self.exception = _Exc
        fake = self

        class Client:
            def __init__(self, account):
                self.account = account

            @classmethod
            def from_credentials(cls, token_id, token_secret):
                fake.clients.append((token_id, token_secret))
                return cls(fake.account(token_id))

        def _check(client):
            if client.account.auth_error:
                raise _Exc.AuthError(client.account.auth_error)

        class _Dict:
            def __init__(self, client):
                self.client = client

            def hydrate(self, client=None):
                _check(self.client)
                return self

            def get(self, key, default=None):
                _check(self.client)
                return self.client.account.state.get(key, default)

            def put(self, key, value, *, skip_if_exists=False):
                _check(self.client)
                if skip_if_exists and key in self.client.account.state:
                    return False
                self.client.account.state[key] = value
                return True

        class Dict:
            @staticmethod
            def from_name(name, *, environment_name=None, create_if_missing=False, client=None):
                return _Dict(client)

        class _Method:
            def __init__(self, client):
                self.client = client

            def spawn(self, request):
                _check(self.client)
                account = self.client.account
                if not account.deployed:
                    raise _Exc.NotFoundError("App 'ingestify-whisper' not found")
                if account.spawn_error is not None:
                    raise account.spawn_error
                protocol.parse_request(request)
                account.spawned.append(request)
                polls, outcome = account.behaviour(request) or (None, None)
                call = FakeCall(account, f"fc-{len(account.spawned)}", polls, outcome)
                account.calls[call.object_id] = call
                account.state.setdefault(protocol.attempt_entry(request["attempt_key"]),
                                         {"container_id": "ta-container-1", "call_id": call.object_id,
                                          "started_unix": 1_000.0})
                return call

        class _Queue:
            def __init__(self, client):
                self.client = client

            def _account(self):
                _check(self.client)
                if self.client.account.queue_error is not None:
                    raise self.client.account.queue_error
                return self.client.account

            def put(self, v, block=True, timeout=None, *, partition=None, partition_ttl=86400):
                self._account().queues.setdefault(partition, []).append(v)

            def get_many(self, n_values, block=True, timeout=None, *, partition=None):
                items = self._account().queues.get(partition, [])
                taken = items[:n_values]
                del items[:n_values]
                return taken

            def clear(self, *, partition=None, all=False):
                account = self._account()
                account.cleared.append(partition)
                account.queues.pop(partition, None)

        class Queue:
            @staticmethod
            def from_name(name, *, environment_name=None, create_if_missing=False, client=None):
                return _Queue(client)

        class Cls:
            @staticmethod
            def from_name(app, name, *, environment_name=None, client=None):
                return lambda: SimpleNamespace(transcribe=_Method(client))

        class _Function:
            def __init__(self, client):
                self.client = client

            def hydrate(self, client=None):
                _check(self.client)
                if not self.client.account.deployed:
                    raise _Exc.NotFoundError("Function 'meta' not found")
                return self

            def remote(self):
                self.hydrate()
                return self.client.account.meta

        class Function:
            @staticmethod
            def from_name(app, name, *, environment_name=None, client=None):
                return _Function(client)

        class FunctionCall:
            @staticmethod
            def from_id(call_id, client=None):
                return client.account.calls[call_id]

        self.Client, self.Dict, self.Cls, self.Function, self.FunctionCall = Client, Dict, Cls, Function, FunctionCall
        self.Queue = Queue

    def account(self, token_id: str) -> Account:
        return self.accounts.setdefault(token_id, Account(token_id))


class Clock:
    """time.time() stand-in that moves forward on every read"""

    def __init__(self, start=1_000.0, step=0.0):
        self.now = start
        self.step = step

    def __call__(self):
        value = self.now
        self.now += self.step
        return value
