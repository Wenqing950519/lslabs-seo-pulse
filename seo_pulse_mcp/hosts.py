from .settings import _host_list, load_settings


def clean_hosts(rows, production_hosts_override=None, settings=None):
    settings = settings or load_settings()
    allowed = set(_host_list(','.join(production_hosts_override)) if production_hosts_override is not None
                  else settings.production_hosts)
    excluded = {"localhost", "127.0.0.1"} | set(settings.exclude_hosts)
    kept = [dict(r) for r in rows if r['hostName'].lower().rstrip('.') in allowed - excluded]
    total = sum(r.get('sessions', 0) for r in rows)
    removed = total - sum(r.get('sessions', 0) for r in kept)
    ratio = removed / total if total else 0
    return kept, {"excluded_sessions": removed, "excluded_ratio": ratio,
                  "pollution_warning": ratio > .20}


def exclude_hosts(rows):
    return clean_hosts(rows)[0]
