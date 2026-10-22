"""How registered tools execute: off the event loop, for one caller, inside cost limits.

The tool functions are synchronous and call Google over blocking HTTP, so each call
runs in a worker thread (bounded by `max_concurrency`) instead of stalling every other
request on the event loop. Hosted call budgets are reserved in a shared atomic
store before Google runs, including across restarts and overlapping revisions.
Concurrency and short result caches remain per process. Local use keeps limits off.
"""
import json
import threading
import time
from collections import OrderedDict, deque

import anyio
import anyio.lowlevel
import anyio.to_thread

from . import events
from .admission import AdmissionUnavailable, LimitExceeded, state_call
from .caller import acting_for

LOCAL_SUBJECT = "local"


class ToolRuntime:
    def __init__(self, max_concurrency=8, per_minute=0, per_day=0, daily_total=0,
                 cache_seconds=0, cache_entries=256, clock=time.monotonic, wall=time.time,
                 shared_store=None, require_shared=False):
        self.max_concurrency = max_concurrency
        self.per_minute, self.per_day, self.daily_total = per_minute, per_day, daily_total
        self.cache_seconds, self.cache_entries = cache_seconds, cache_entries
        self._clock, self._wall = clock, wall
        self.shared_store, self.require_shared = shared_store, require_shared
        # One limiter per event loop: a limiter bound to another loop would block forever.
        self._limiter = anyio.lowlevel.RunVar(f"seo_pulse_limiter_{id(self)}")
        self._lock = threading.Lock()
        self._recent = {}  # subject -> deque of call times within the last minute
        self._daily = {}  # (day, subject) -> count; (day, None) -> process total
        self._cache = OrderedDict()  # key -> (expires_at, result)

    def _day(self):
        return int(self._wall() // 86400)

    def _admit(self, subject):
        """Count one call and return today's process total, or raise the limit the caller hit."""
        now, day = self._clock(), self._day()
        with self._lock:
            for key in [k for k in self._daily if k[0] != day]:
                del self._daily[key]
            if self.daily_total and self._daily.get((day, None), 0) >= self.daily_total:
                raise LimitExceeded("daily_total", "SEO Pulse 今日的總呼叫量已達上限，請明天再試。")
            if self.per_day and self._daily.get((day, subject), 0) >= self.per_day:
                raise LimitExceeded("per_day", f"你今日已使用 {self.per_day} 次 SEO Pulse 工具，已達上限，請明天再試。")
            recent = self._recent.setdefault(subject, deque())
            while recent and now - recent[0] >= 60:
                recent.popleft()
            if self.per_minute and len(recent) >= self.per_minute:
                raise LimitExceeded("per_minute", f"呼叫太頻繁：每分鐘最多 {self.per_minute} 次，請稍後再試。")
            recent.append(now)
            self._daily[(day, subject)] = self._daily.get((day, subject), 0) + 1
            self._daily[(day, None)] = self._daily.get((day, None), 0) + 1
            return self._daily[(day, None)]

    def _cache_key(self, subject, name, arguments):
        return subject, name, json.dumps(arguments, sort_keys=True, ensure_ascii=False, default=str)

    def _cached(self, key):
        with self._lock:
            hit = self._cache.get(key)
            if hit and hit[0] > self._clock():
                self._cache.move_to_end(key)
                return True, hit[1]
            self._cache.pop(key, None)
            return False, None

    def _store(self, key, result):
        with self._lock:
            self._cache[key] = (self._clock() + self.cache_seconds, result)
            while len(self._cache) > self.cache_entries:
                self._cache.popitem(last=False)

    async def run(self, name, function, arguments, caller):
        subject = caller.subject if caller else LOCAL_SUBJECT
        # Only hosted calls are logged; local stdio users get no stderr noise.
        log = (lambda outcome, severity="INFO", **fields: events.emit(
            "tool_call", severity, tool=name, outcome=outcome, subject=events.subject_hash(subject), **fields)
        ) if caller is not None else (lambda *a, **k: None)
        started = self._clock()
        if caller is not None and self.require_shared and self.shared_store is None:
            log("error", "ERROR", error_type="AdmissionUnavailable")
            raise AdmissionUnavailable()
        key = self._cache_key(subject, name, arguments) if self.cache_seconds else None
        if key:
            hit, result = self._cached(key)
            if hit:
                if caller is not None and self.shared_store is not None:
                    try:
                        await state_call(self.shared_store.check_available)
                    except AdmissionUnavailable:
                        log("error", "ERROR", error_type="AdmissionUnavailable")
                        raise
                log("cached")
                return result
        day_total = None
        try:
            limiter = self._limiter.get()
        except LookupError:
            limiter = anyio.CapacityLimiter(self.max_concurrency)
            self._limiter.set(limiter)

        def call():
            with acting_for(caller):
                return function(**arguments)

        try:
            async with limiter:
                if caller is not None:
                    if self.shared_store is not None:
                        day_total = await state_call(lambda: self.shared_store.admit(
                            subject, per_minute=self.per_minute, per_day=self.per_day, daily_total=self.daily_total))
                    else:
                        day_total = self._admit(subject)
                result = await anyio.to_thread.run_sync(call)
        except LimitExceeded as exc:
            log("limited", "WARNING", limit=exc.limit)
            raise
        except Exception as exc:
            # Bad tool input is the caller's problem; anything else needs attention.
            log("error", "WARNING" if isinstance(exc, ValueError) else "ERROR", error_type=type(exc).__name__,
                duration_ms=round((self._clock() - started) * 1000), day_total=day_total)
            raise
        if key:
            self._store(key, result)
        log("ok", duration_ms=round((self._clock() - started) * 1000), day_total=day_total)
        return result
