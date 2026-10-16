"""Small, independently written adapters for Google's read-only reporting APIs."""
import json
import os
import tempfile
from datetime import date, datetime
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.analytics.data_v1beta import BetaAnalyticsDataClient

from .base import GSCConnector, GA4Connector

GSC_SCOPES = ("https://www.googleapis.com/auth/webmasters.readonly",)
GA4_SCOPES = ("https://www.googleapis.com/auth/analytics.readonly",)
AUTH_REQUIRED = "Google 授權無效或尚未設定，請先執行 seo-pulse auth。"


def _save_token(path, credentials):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Atomic replacement with owner-only permissions, including existing caches.
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(credentials.to_json())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _credentials(service, *, interactive=False):
    scopes = {"gsc": GSC_SCOPES, "ga4": GA4_SCOPES}[service]
    path = Path(os.environ.get("SEO_PULSE_TOKEN_DIR", "~/.config/seo-pulse/tokens")).expanduser() / f"{service}.json"
    credentials = None
    if path.is_file():
        try:
            # Check stored grants before loading: never reuse broader scopes.
            info = json.loads(path.read_text(encoding="utf-8"))
            if set(info.get("scopes", [])) == set(scopes):
                credentials = Credentials.from_authorized_user_info(info, scopes=list(scopes))
        except (ValueError, KeyError):
            credentials = None
    if credentials and credentials.expired and credentials.refresh_token:
        try:
            credentials.refresh(Request())
            _save_token(path, credentials)
        except RefreshError:
            credentials = None
    if credentials and credentials.valid:
        return credentials
    if not interactive:
        raise RuntimeError(AUTH_REQUIRED)
    secret = os.environ.get("SEO_PULSE_GOOGLE_CLIENT_SECRET")
    if not secret or not Path(secret).expanduser().is_file():
        raise RuntimeError("請設定 SEO_PULSE_GOOGLE_CLIENT_SECRET，指向 repo 外的 OAuth Desktop client_secret JSON 檔案。")
    flow = InstalledAppFlow.from_client_secrets_file(str(Path(secret).expanduser()), scopes=list(scopes))
    credentials = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    _save_token(path, credentials)
    return credentials


def authenticate():
    """Interactive entry point called only by the explicit auth CLI command."""
    for service in ("gsc", "ga4"):
        _credentials(service, interactive=True)


def _dates(start, end):
    if date.fromisoformat(start) > date.fromisoformat(end):
        raise ValueError("start_date must be <= end_date")


class GoogleGSCConnector(GSCConnector):
    def __init__(self, client_factory=None, site_url=None):
        self.client_factory = client_factory or build
        self.site_url = site_url

    def _client(self):
        return self.client_factory("searchconsole", "v1", credentials=_credentials("gsc"), cache_discovery=False)

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
    def __init__(self, client_factory=None, property_id=None):
        self.client_factory = client_factory or BetaAnalyticsDataClient
        self.property_id = property_id

    def report(self, start_date, end_date):
        _dates(start_date, end_date)
        property_id = self.property_id or os.environ.get("SEO_PULSE_GA4_PROPERTY_ID")
        if not property_id:
            raise RuntimeError("請設定 SEO_PULSE_GA4_PROPERTY_ID。")
        client = self.client_factory(credentials=_credentials("ga4"))
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
