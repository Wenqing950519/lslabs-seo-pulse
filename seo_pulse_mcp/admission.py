"""Atomic hosted admission and code replay protection; no Google grants are stored.

The backend owns transactions. The policy is identical for every process/revision;
local stdio mode never constructs this store. Firestore TTL is cleanup only, never
an authorization decision. Callers must keep the namespace and HMAC key stable.
"""
from datetime import datetime, timezone
import hashlib
import hmac
import re
import threading
import time

import anyio

COLLECTION = "seo_pulse_state"
STATE_TIMEOUT_SECONDS = 8
_STATE_WORKERS = threading.BoundedSemaphore(8)


class AdmissionUnavailable(RuntimeError):
    def __init__(self):
        super().__init__("SEO Pulse 的使用量驗證服務暫時無法使用，請稍後再試。")


class LimitExceeded(RuntimeError):
    """The call was refused before invoking its Google connector."""

    def __init__(self, limit, message):
        super().__init__(message)
        self.limit = limit


async def state_call(function):
    """Bound request waiting; a late transaction may debit, but cannot run Google.

    A timed-out blocking RPC can finish in its worker thread. Its only possible
    effect is a conservative counter/code claim; the caller never proceeds.
    """
    def bounded_call():
        # Cancellation cannot stop a synchronous SDK RPC. Keep at most eight
        # such operations alive per process, even after callers time out.
        if not _STATE_WORKERS.acquire(blocking=False):
            raise AdmissionUnavailable()
        try:
            return function()
        finally:
            _STATE_WORKERS.release()

    try:
        with anyio.fail_after(STATE_TIMEOUT_SECONDS):
            return await anyio.to_thread.run_sync(bounded_call, abandon_on_cancel=True)
    except TimeoutError:
        raise AdmissionUnavailable() from None


class SharedAdmissionStore:
    def __init__(self, backend, *, namespace, hmac_key, clock=time.time):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", namespace):
            raise ValueError("SEO_PULSE_STATE_NAMESPACE 必須是 1–80 個英數字、底線或連字號。")
        if len(hmac_key.encode()) < 32:
            raise ValueError("SEO_PULSE_STATE_HMAC_KEY 必須至少 32 bytes。")
        self.backend, self.namespace, self._clock = backend, namespace, clock
        self._key = hmac_key.encode()

    def _id(self, kind, value=""):
        digest = hmac.new(self._key, f"{self.namespace}|{kind}|{value}".encode(), hashlib.sha256).hexdigest()
        return f"{self.namespace}-{kind}-{digest}"

    def _run(self, operation):
        try:
            return self.backend.run(operation)
        except (LimitExceeded, AdmissionUnavailable):
            raise
        except Exception:
            raise AdmissionUnavailable() from None

    def check_available(self):
        """A read-only transaction: no counter debit, user record or provider call."""
        self._run(lambda tx: tx.read(self._id("global")))

    def admit(self, subject, *, per_minute, per_day, daily_total):
        if min(per_minute, per_day, daily_total) <= 0:
            raise AdmissionUnavailable()

        def reserve(tx):
            now = self._clock()
            day = int(now // 86400)
            global_id, user_id = self._id("global"), self._id("user", subject)
            total, user = tx.read(global_id), tx.read(user_id)
            # A clock moving backwards must not reset a newer day's budget.
            if total.get("day", day) > day or user.get("day", day) > day:
                raise AdmissionUnavailable()
            total_count = total.get("count", 0) if total.get("day") == day else 0
            user_count = user.get("count", 0) if user.get("day") == day else 0
            recent = [stamp for stamp in user.get("recent", []) if now - stamp < 60]
            if total_count >= daily_total:
                raise LimitExceeded("daily_total", "SEO Pulse 今日的總呼叫量已達上限，請明天再試。")
            if user_count >= per_day:
                raise LimitExceeded("per_day", f"你今日已使用 {per_day} 次 SEO Pulse 工具，已達上限，請明天再試。")
            if len(recent) >= per_minute:
                raise LimitExceeded("per_minute", f"呼叫太頻繁：每分鐘最多 {per_minute} 次，請稍後再試。")
            expiry = datetime.fromtimestamp((day + 2) * 86400, timezone.utc)
            tx.write(global_id, {"day": day, "count": total_count + 1, "expire_at": expiry})
            tx.write(user_id, {"day": day, "count": user_count + 1, "recent": [*recent, now], "expire_at": expiry})
            return total_count + 1

        return self._run(reserve)

    def claim_code(self, code, expires_at):
        def claim(tx):
            if expires_at <= self._clock():
                return False
            key = self._id("code", code)
            if tx.read(key):
                return False
            tx.write(key, {"expire_at": datetime.fromtimestamp(expires_at + 60, timezone.utc)})
            return True

        return self._run(claim)


class FirestoreBackend:
    """Firestore Native transactions; import/ADC only when hosted mode constructs it."""

    def __init__(self, project, database="(default)", client=None):
        from google.cloud import firestore
        self._firestore = firestore
        self._client = client or firestore.Client(project=project, database=database)
        self._collection = self._client.collection(COLLECTION)

    def run(self, operation):
        collection = self._collection

        @self._firestore.transactional
        def execute(transaction):
            class Transaction:
                def read(self, key):
                    snapshot = collection.document(key).get(transaction=transaction, retry=None, timeout=3)
                    return snapshot.to_dict() or {}

                def write(self, key, data):
                    transaction.set(collection.document(key), data)

            return operation(Transaction())

        return execute(self._client.transaction(max_attempts=3))
