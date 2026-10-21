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
    local_provider,
)


def _dates(start, end):
    if date.fromisoformat(start) > date.fromisoformat(end):
        raise ValueError("start_date must be <= end_date")


class GoogleGSCConnector(GSCConnector):
    def __init__(self, client_factory=None, site_url=None, credential_provider=None, credential_context=None):
        self.client_factory = client_factory or build
        self.site_url = site_url
        self.credential_provider = credential_provider or local_provider()
        self.credential_context = credential_context

    def _client(self):
        credentials = self.credential_provider.get("gsc", self.credential_context)
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
    def __init__(self, client_factory=None, property_id=None, credential_provider=None,
                 credential_context=None, admin_factory=None):
        self.client_factory = client_factory or BetaAnalyticsDataClient
        self.admin_factory = admin_factory or build
        self.property_id = property_id
        self.credential_provider = credential_provider or local_provider()
        self.credential_context = credential_context

    def list_properties(self):
        """GA4 properties this Google account can read (Analytics Admin API, read-only scope)."""
        credentials = self.credential_provider.get("ga4", self.credential_context)
        admin = self.admin_factory("analyticsadmin", "v1beta", credentials=credentials, cache_discovery=False)
        result, token = [], None
        while True:
            try:
                page = admin.accountSummaries().list(pageSize=200, pageToken=token).execute()
            except Exception as exc:  # googleapiclient.errors.HttpError; kept generic for the optional extra
                if "SERVICE_DISABLED" in str(exc) or "has not been used" in str(exc):
                    raise RuntimeError("Google Cloud 專案尚未啟用 Google Analytics Admin API，"
                                       "請改從 GA4「管理 → 資源設定」查詢資源 ID。") from None
                raise
            for account in page.get("accountSummaries", []):
                for prop in account.get("propertySummaries", []):
                    result.append({"property_id": prop["property"].split("/")[-1],
                                   "display_name": prop.get("displayName", ""),
                                   "account_name": account.get("displayName", "")})
            token = page.get("nextPageToken")
            if not token:
                return result

    def report(self, start_date, end_date):
        _dates(start_date, end_date)
        property_id = self.property_id or os.environ.get("SEO_PULSE_GA4_PROPERTY_ID")
        if not property_id:
            raise RuntimeError("請設定 SEO_PULSE_GA4_PROPERTY_ID。")
        client = self.client_factory(credentials=self.credential_provider.get("ga4", self.credential_context))
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
