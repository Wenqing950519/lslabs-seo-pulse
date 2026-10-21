"""How registered tools execute: off the event loop, for one caller, inside cost limits.

The tool functions are synchronous and call Google over blocking HTTP, so each call
runs in a worker thread (bounded by `max_concurrency`) instead of stalling every other
request on the event loop. In hosted mode the same layer enforces per-caller and
per-process call limits and serves identical calls from a short in-memory cache, which
is what keeps Cloud Run CPU time and Google API quota bounded. Local use keeps all
limits off. Counters live in process memory: with one Cloud Run instance they are exact.
"""
import json
import threading
import time
from collections import OrderedDict, deque

import anyio
import anyio.lowlevel
import anyio.to_thread

from .caller import acting_for

LOCAL_SUBJECT = "local"


class ToolRuntime:
    def __init__(self, max_concurrency=8, per_minute=0, per_day=0, daily_total=0,
                 cache_seconds=0, cache_entries=256, clock=time.monotonic, wall=time.time):
        self.max_concurrency = max_concurrency
        self.per_minute, self.per_day, self.daily_total = per_minute, per_day, daily_total
        self.cache_seconds, self.cache_entries = cache_seconds, cache_entries
        self._clock, self._wall = clock, wall
        # One limiter per event loop: a limiter bound to another loop would block forever.
        self._limiter = anyio.lowlevel.RunVar(f"seo_pulse_limiter_{id(self)}")
        self._lock = threading.Lock()
        self._recent = {}  # subject -> deque of call times within the last minute
        self._daily = {}  # (day, subject) -> count; (day, None) -> process total
        self._cache = OrderedDict()  # key -> (expires_at, result)

    def _day(self):
        return int(self._wall() // 86400)

    def _admit(self, subject):
        """Count one call or raise the limit the caller hit (Traditional Chinese)."""
        now, day = self._clock(), self._day()
        with self._lock:
            for key in [k for k in self._daily if k[0] != day]:
                del self._daily[key]
            if self.daily_total and self._daily.get((day, None), 0) >= self.daily_total:
                raise RuntimeError("SEO Pulse 今日的總呼叫量已達上限，請明天再試。")
            if self.per_day and self._daily.get((day, subject), 0) >= self.per_day:
                raise RuntimeError(f"你今日已使用 {self.per_day} 次 SEO Pulse 工具，已達上限，請明天再試。")
            recent = self._recent.setdefault(subject, deque())
            while recent and now - recent[0] >= 60:
                recent.popleft()
            if self.per_minute and len(recent) >= self.per_minute:
                raise RuntimeError(f"呼叫太頻繁：每分鐘最多 {self.per_minute} 次，請稍後再試。")
            recent.append(now)
            self._daily[(day, subject)] = self._daily.get((day, subject), 0) + 1
            self._daily[(day, None)] = self._daily.get((day, None), 0) + 1

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
        key = self._cache_key(subject, name, arguments) if self.cache_seconds else None
        if key:
            hit, result = self._cached(key)
            if hit:
                return result
        if caller is not None:
            self._admit(subject)
        try:
            limiter = self._limiter.get()
        except LookupError:
            limiter = anyio.CapacityLimiter(self.max_concurrency)
            self._limiter.set(limiter)

        def call():
            with acting_for(caller):
                return function(**arguments)

        result = await anyio.to_thread.run_sync(call, limiter=limiter)
        if key:
            self._store(key, result)
        return result
