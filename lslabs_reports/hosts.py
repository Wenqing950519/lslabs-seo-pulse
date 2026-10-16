import os
from .rules import RULES


def clean_hosts(rows, production_hosts=None):
    allowed = {h.lower().rstrip('.') for h in (production_hosts if production_hosts is not None
               else os.getenv('LSLABS_PRODUCTION_HOSTS', ','.join(RULES['production_hosts'])).split(','))}
    excluded = {"localhost", "127.0.0.1"} | {
        h.strip().lower().rstrip('.') for h in os.getenv('LSLABS_EXCLUDE_HOSTS', '').split(',')}
    kept = [dict(r) for r in rows if r['hostName'].lower().rstrip('.') in allowed - excluded]
    total = sum(r.get('sessions', 0) for r in rows)
    removed = total - sum(r.get('sessions', 0) for r in kept)
    ratio = removed / total if total else 0
    return kept, {"excluded_sessions": removed, "excluded_ratio": ratio,
                  "pollution_warning": ratio > .20}


def exclude_hosts(rows):
    return clean_hosts(rows)[0]
