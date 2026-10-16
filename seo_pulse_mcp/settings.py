"""Runtime settings read from SEO_PULSE_* environment variables in one place."""
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .rules import RULES

CONNECTORS = ("fixture", "google")


def _host_list(value):
    return tuple(h.strip().lower().rstrip('.') for h in value.split(',') if h.strip())


@dataclass(frozen=True)
class Settings:
    connector: str
    production_hosts: tuple
    exclude_hosts: tuple
    canonical_origin: str
    timezone: str
    gsc_lag_days: int
    ctr_benchmarks_path: str | None

    @property
    def uses_default_hosts(self):
        return list(self.production_hosts) == RULES['production_hosts']

    def default_end_date(self, now=None) -> date:
        """Today in the report timezone minus the GSC data lag."""
        now = now or datetime.now(ZoneInfo(self.timezone))
        return now.astimezone(ZoneInfo(self.timezone)).date() - timedelta(days=self.gsc_lag_days)


def load_settings(env=None) -> Settings:
    env = os.environ if env is None else env
    connector = env.get('SEO_PULSE_CONNECTOR', 'fixture')
    if connector not in CONNECTORS:
        raise ValueError("SEO_PULSE_CONNECTOR must be fixture or google")
    hosts = _host_list(env.get('SEO_PULSE_PRODUCTION_HOSTS', ','.join(RULES['production_hosts'])))
    origin = env.get('SEO_PULSE_CANONICAL_ORIGIN', '').strip().rstrip('/')
    origin = origin or (f'https://{hosts[0]}' if hosts else RULES['canonical_origin'])
    timezone = env.get('SEO_PULSE_TIMEZONE', RULES['timezone'])
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError(f"SEO_PULSE_TIMEZONE 不是有效的 IANA 時區：{timezone}") from None
    try:
        lag = int(env.get('SEO_PULSE_GSC_LAG_DAYS', RULES['gsc_lag_days']))
    except ValueError:
        raise ValueError("SEO_PULSE_GSC_LAG_DAYS 必須是整數天數。") from None
    return Settings(connector=connector, production_hosts=hosts,
                    exclude_hosts=_host_list(env.get('SEO_PULSE_EXCLUDE_HOSTS', '')),
                    canonical_origin=origin, timezone=timezone, gsc_lag_days=lag,
                    ctr_benchmarks_path=env.get('SEO_PULSE_CTR_BENCHMARKS_PATH') or None)
