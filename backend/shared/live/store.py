"""Redis reservations/tickets. Expiring slots avoid counters stranded by a crash.

WATCH transactions fence every mutation with a random generation. The worker's
process-local active guard also refuses overlapping decoders when a lease expires.
"""
import hashlib
import json
import secrets
from redis.exceptions import WatchError
from shared.live.protocol import LiveError


def dumps(value):
    return json.dumps(value, separators=(',', ':'))


class LiveStore:
    def __init__(self, redis, worker_id='live-local'):
        self.redis, self.worker_id = redis, worker_id

    @property
    def worker_key(self):
        return f'live:worker:{self.worker_id}'

    def ready(self, data):
        self.redis.set(self.worker_key, dumps(data), ex=10)

    def readiness(self):
        value = self.redis.get(self.worker_key)
        return json.loads(value) if value else None

    def reserve(self, job_id):
        generation = secrets.randbits(63) or 1
        for _ in range(20):
            with self.redis.pipeline() as p:
                try:
                    p.watch(self.worker_key)
                    raw = p.get(self.worker_key)
                    worker = json.loads(raw) if raw else None
                    if not worker or not worker.get('ready'):
                        raise LiveError('LIVE_NOT_READY', 1013)
                    # A released/expired lease can precede the return of an
                    # in-flight CUDA call. Keep admission closed while that
                    # process-local decoder still occupies the worker.
                    active_keys = [f'live:lease:{job}' for job in worker.get('active_jobs', [])]
                    if active_keys:
                        p.watch(*active_keys)
                        if any(p.get(key) is None for key in active_keys):
                            raise LiveError('LIVE_CAPACITY_FULL', 1013)
                    slots = [f'live:slot:{self.worker_id}:{i}' for i in range(worker['capacity'])]
                    p.watch(*slots)
                    slot = next((key for key in slots if p.get(key) is None), None)
                    if slot is None:
                        raise LiveError('LIVE_CAPACITY_FULL', 1013)
                    lease = {'job_id': job_id, 'worker_id': self.worker_id, 'generation': generation,
                             'slot': slot, 'incarnation': worker['incarnation'], 'phase': 'created'}
                    p.multi()
                    p.set(slot, dumps(lease), ex=60)
                    p.set(f'live:lease:{job_id}', dumps(lease), ex=60)
                    p.execute()
                    return lease, worker
                except WatchError:
                    continue
        raise LiveError('LIVE_CAPACITY_FULL', 1013)

    def lease(self, job_id):
        raw = self.redis.get(f'live:lease:{job_id}')
        return json.loads(raw) if raw else None

    def valid(self, job_id, generation, phase=None):
        lease = self.lease(job_id)
        if not lease or lease['generation'] != generation or (phase and lease['phase'] != phase):
            return False
        slot = self.redis.get(lease['slot'])
        worker = self.readiness()
        return bool(slot and json.loads(slot) == lease and worker and worker.get('ready')
                    and worker['incarnation'] == lease['incarnation'])

    def renew(self, job_id, generation, activate=False):
        key = f'live:lease:{job_id}'
        for _ in range(20):
            with self.redis.pipeline() as p:
                try:
                    p.watch(key, self.worker_key)
                    raw, wr = p.get(key), p.get(self.worker_key)
                    lease, worker = (json.loads(raw) if raw else None), (json.loads(wr) if wr else None)
                    if not lease or lease['generation'] != generation or not worker or not worker.get('ready') or worker['incarnation'] != lease['incarnation']:
                        return False
                    if activate and lease['phase'] != 'created':
                        return False
                    p.watch(lease['slot'])
                    if p.get(lease['slot']) != raw:
                        return False
                    if activate:
                        lease['phase'] = 'streaming'
                    p.multi()
                    p.set(key, dumps(lease), ex=45)
                    p.set(lease['slot'], dumps(lease), ex=45)
                    p.execute()
                    return True
                except WatchError:
                    continue
        return False

    def release(self, job_id, generation):
        key = f'live:lease:{job_id}'
        for _ in range(20):
            with self.redis.pipeline() as p:
                try:
                    p.watch(key)
                    raw = p.get(key)
                    if not raw:
                        return
                    lease = json.loads(raw)
                    if lease['generation'] != generation:
                        return
                    p.watch(lease['slot'])
                    same = p.get(lease['slot']) == raw
                    p.multi()
                    p.delete(key)
                    if same:
                        p.delete(lease['slot'])
                    p.execute()
                    return
                except WatchError:
                    continue
        raise LiveError('LIVE_STORE_UNAVAILABLE', 1011)

    def ticket(self, lease, user_id):
        ticket = secrets.token_urlsafe(32)
        key = 'live:ticket:' + hashlib.sha256(ticket.encode()).hexdigest()
        self.redis.set(key, dumps({**lease, 'user_id': user_id}), ex=60)
        return ticket

    def consume(self, ticket, job_id):
        if not isinstance(ticket, str) or not 32 <= len(ticket) <= 128:
            raise LiveError('LIVE_INVALID_TICKET', 4401)
        key = 'live:ticket:' + hashlib.sha256(ticket.encode()).hexdigest()
        # GETDEL is atomic on Redis >= 6.2 (deployment uses Redis 7).
        raw = self.redis.getdel(key)
        value = json.loads(raw) if raw else None
        if not value or value['job_id'] != job_id or not self.valid(job_id, value['generation'], 'created'):
            raise LiveError('LIVE_INVALID_TICKET', 4401)
        return value

    def append_confirmed(self, job_id, generation, segments):
        """Same partial list/schema/TTL as RedisClient, fenced atomically."""
        lease_key, partial = f'live:lease:{job_id}', f'job:{job_id}:transcript:partial'
        for _ in range(20):
            with self.redis.pipeline() as p:
                try:
                    p.watch(lease_key)
                    raw = p.get(lease_key)
                    if not raw or json.loads(raw)['generation'] != generation:
                        raise LiveError('LIVE_LEASE_LOST', 1011)
                    p.multi()
                    if segments:
                        p.rpush(partial, *[dumps(s) for s in segments])
                        p.expire(partial, 86400)
                    p.execute()
                    return
                except WatchError:
                    continue
        raise LiveError('LIVE_STORE_UNAVAILABLE', 1011)
