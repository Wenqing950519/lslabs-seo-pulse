from .settings import _host_list, load_settings

SUBDOMAIN_HOST_LIMIT = 5


def property_domain(site_url):
    """The domain a `sc-domain:` GSC property covers (subdomains included), else None.

    URL-prefix properties cover a single origin, so they have no sibling subdomains.
    """
    if not site_url or not site_url.startswith("sc-domain:"):
        return None
    domain = site_url[len("sc-domain:"):].strip().lower().rstrip('.')
    return domain[4:] if domain.startswith("www.") else domain or None


def clean_hosts(rows, production_hosts_override=None, settings=None):
    """Keep production-host rows and measure what was dropped.

    Sessions on other subdomains of a domain property are excluded like any other
    host, but reported as `subdomain_sessions` instead of pollution: Search Console
    counts them, so they are a scope choice (pass production_hosts to include them),
    not test traffic.
    """
    settings = settings or load_settings()
    allowed = set(_host_list(','.join(production_hosts_override)) if production_hosts_override is not None
                  else settings.production_hosts)
    excluded = {"localhost", "127.0.0.1"} | set(settings.exclude_hosts)
    domain = property_domain(settings.gsc_site_url)
    kept, sibling_sessions, sibling_hosts = [], 0, {}
    for row in rows:
        host = row['hostName'].lower().rstrip('.')
        if host in allowed - excluded:
            kept.append(dict(row))
        elif domain and host not in excluded and (host == domain or host.endswith('.' + domain)):
            sibling_sessions += row.get('sessions', 0)
            sibling_hosts[host] = sibling_hosts.get(host, 0) + row.get('sessions', 0)
    total = sum(r.get('sessions', 0) for r in rows)
    removed = total - sum(r.get('sessions', 0) for r in kept)
    ratio = removed / total if total else 0
    pollution = (removed - sibling_sessions) / total if total else 0
    top_siblings = sorted(sibling_hosts, key=lambda h: (-sibling_hosts[h], h))[:SUBDOMAIN_HOST_LIMIT]
    return kept, {"excluded_sessions": removed, "excluded_ratio": ratio,
                  "subdomain_sessions": sibling_sessions, "subdomain_hosts": top_siblings,
                  "pollution_ratio": pollution, "pollution_warning": pollution > .20}


def exclude_hosts(rows, production_hosts_override=None, settings=None):
    return clean_hosts(rows, production_hosts_override, settings)[0]
