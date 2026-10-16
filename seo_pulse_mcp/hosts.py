import os
from .rules import RULES


def _host_list(value):
    return [h.strip().lower().rstrip('.') for h in value.split(',') if h.strip()]


def production_hosts():
    return _host_list(os.getenv('SEO_PULSE_PRODUCTION_HOSTS', ','.join(RULES['production_hosts'])))


def canonical_origin():
    """Explicit SEO_PULSE_CANONICAL_ORIGIN, else https:// plus the first production host."""
    explicit = os.getenv('SEO_PULSE_CANONICAL_ORIGIN', '').strip()
    if explicit:
        return explicit.rstrip('/')
    hosts = production_hosts()
    return f'https://{hosts[0]}' if hosts else RULES['canonical_origin']


def clean_hosts(rows, production_hosts_override=None):
    allowed = set(_host_list(','.join(production_hosts_override)) if production_hosts_override is not None
                  else production_hosts())
    excluded = {"localhost", "127.0.0.1"} | set(_host_list(os.getenv('SEO_PULSE_EXCLUDE_HOSTS', '')))
    kept = [dict(r) for r in rows if r['hostName'].lower().rstrip('.') in allowed - excluded]
    total = sum(r.get('sessions', 0) for r in rows)
    removed = total - sum(r.get('sessions', 0) for r in kept)
    ratio = removed / total if total else 0
    return kept, {"excluded_sessions": removed, "excluded_ratio": ratio,
                  "pollution_warning": ratio > .20}


def exclude_hosts(rows):
    return clean_hosts(rows)[0]
