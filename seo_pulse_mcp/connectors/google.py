"""Small, independently written adapters for Google's read-only reporting APIs."""
import os
from datetime import date, datetime

from googleapiclient.discovery import build
from google.analytics.data_v1beta import BetaAnalyticsDataClient

from .base import GSCConnector, GA4Connector
from .credentials import (  # noqa: F401 (re-exported for backward-compatible access)
    AUTH_REQUIRED,
    GA4_SCOPES,
    GSC_SCOPES,
    CredentialProvider,
    LocalFileCredentialProvider,
    _credentials,
    authenticate,
)


def _dates(start, end):
    if date.fromisoformat(start) > date.fromisoformat(end):
        raise ValueError("start_date must be <= end_date")


class GoogleGSCConnector(GSCConnector):
    def __init__(self, client_factory=None, site_url=None, credential_provider=None):
        self.client_factory = client_factory or build
        self.site_url = site_url
        self.credential_provider = credential_provider or LocalFileCredentialProvider()

    def _client(self):
        credentials = self.credential_provider.get("gsc", None)
        return self.client_factory("searchconsole", "v1", credentials=credentials, cache_discovery=False)

    def list_sites(self):
        return self._client().sites().list().execute().get("siteEntry", [])

    def query(self, start_date, end_date, dimensions, filters=None):
        _dates(start_date, end_date)
        allowed = {"date", "query", "page"}
        if not set(dimensions) <= allowed or not set(filters or {}) <= allowed:
            raise ValueError("Supported dimensions/filters: date, query, page (exact match)")
        site = self.site_url or os.environ.get("SEO_PULSE_GSC_SITE_URL")
        if not site:
            raise RuntimeError("請設定 SEO_PULSE_GSC_SITE_URL（例如 sc-domain:example.com）。")
        client = self._client()
        body = {"startDate": start_date, "endDate": end_date,
                "dimensions": list(dimensions), "rowLimit": 25000, "startRow": 0}
        if filters:
            body["dimensionFilterGroups"] = [{"filters": [
                {"dimension": key, "operator": "equals", "expression": value}
                for key, value in filters.items()]}]
        result = []
        while True:
            rows = client.searchanalytics().query(siteUrl=site, body=dict(body)).execute().get("rows", [])
            for row in rows:
                clicks, impressions = row.get("clicks", 0), row.get("impressions", 0)
                result.append({**dict(zip(dimensions, row.get("keys", []))),
                               "clicks": clicks, "impressions": impressions,
                               "position": row.get("position", 0),
                               "ctr": clicks / impressions if impressions else 0})
            if len(rows) < 25000:
                return result
            body["startRow"] += len(rows)


class GoogleGA4Connector(GA4Connector):
    def __init__(self, client_factory=None, property_id=None, credential_provider=None):
        self.client_factory = client_factory or BetaAnalyticsDataClient
        self.property_id = property_id
        self.credential_provider = credential_provider or LocalFileCredentialProvider()

    def report(self, start_date, end_date):
        _dates(start_date, end_date)
        property_id = self.property_id or os.environ.get("SEO_PULSE_GA4_PROPERTY_ID")
        if not property_id:
            raise RuntimeError("請設定 SEO_PULSE_GA4_PROPERTY_ID。")
        client = self.client_factory(credentials=self.credential_provider.get("ga4", None))
        dimensions = ["date", "hostName", "sessionDefaultChannelGroup", "sessionSource"]
        metrics = ["sessions", "keyEvents"]
        result, offset = [], 0
        while True:
            response = client.run_report(request={
                "property": f"properties/{property_id}",
                "date_ranges": [{"start_date": start_date, "end_date": end_date}],
                "dimensions": [{"name": name} for name in dimensions],
                "metrics": [{"name": name} for name in metrics],
                "limit": 25000, "offset": offset})
            for row in response.rows:
                item = dict(zip(dimensions, (v.value for v in row.dimension_values)))
                item["date"] = datetime.strptime(item["date"], "%Y%m%d").date().isoformat()
                item.update(sessions=int(row.metric_values[0].value), keyEvents=float(row.metric_values[1].value))
                result.append(item)
            offset += len(response.rows)
            if not response.rows or offset >= response.row_count:
                return result
