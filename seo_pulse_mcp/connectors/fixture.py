import json
from datetime import date
from pathlib import Path
from .base import GSCConnector, GA4Connector

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "sample.json"


def date_rows(rows, start_date, end_date):
    start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    if start > end:
        raise ValueError("start_date must be <= end_date")
    return [dict(row) for row in rows if start <= date.fromisoformat(row["date"]) <= end]


class FixtureGSCConnector(GSCConnector):
    def __init__(self, path=DEFAULT_PATH):
        self.data = json.loads(Path(path).read_text(encoding="utf-8"))

    def list_sites(self):
        return self.data["sites"]

    def query(self, start_date, end_date, dimensions, filters=None):
        allowed = {"date", "query", "page"}
        if not set(dimensions) <= allowed or not set(filters or {}) <= allowed:
            raise ValueError("Supported dimensions/filters: date, query, page (exact match)")
        rows = date_rows(self.data["gsc"], start_date, end_date)
        rows = [r for r in rows if all(r.get(k) == v for k, v in (filters or {}).items())]
        grouped = {}
        for row in rows:
            key = tuple(row[d] for d in dimensions)
            item = grouped.setdefault(key, {**dict(zip(dimensions, key)), "clicks": 0,
                                           "impressions": 0, "position": 0})
            item["clicks"] += row["clicks"]
            item["impressions"] += row["impressions"]
            item["position"] += row["position"] * row["impressions"]
        for item in grouped.values():
            item["position"] = item["position"] / item["impressions"] if item["impressions"] else 0
            item["ctr"] = item["clicks"] / item["impressions"] if item["impressions"] else 0
        return list(grouped.values())


class FixtureGA4Connector(GA4Connector):
    def __init__(self, path=DEFAULT_PATH):
        self.data = json.loads(Path(path).read_text(encoding="utf-8"))

    def report(self, start_date, end_date):
        return date_rows(self.data["ga4"], start_date, end_date)
