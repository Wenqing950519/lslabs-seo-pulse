"""Who the current tool call is for.

`None` is the local single-user setup (stdio plugin or local HTTP): credentials come
from the token files on this machine. The hosted server sets a `Caller` for every
authenticated request so connectors use that person's Google authorization.
"""
import contextvars
from contextlib import contextmanager
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Caller:
    subject: str  # Google's stable `sub`; emails can change, `sub` does not
    google_refresh_token: str = field(repr=False)
    email: str | None = field(default=None, repr=False)


_current = contextvars.ContextVar("seo_pulse_caller", default=None)


def current_caller():
    return _current.get()


@contextmanager
def acting_for(caller):
    token = _current.set(caller)
    try:
        yield caller
    finally:
        _current.reset(token)
