from ..settings import load_settings
from .fixture import FixtureGSCConnector, FixtureGA4Connector


def get_connectors(settings=None):
    settings = settings or load_settings()
    if settings.connector == "fixture":
        return FixtureGSCConnector(), FixtureGA4Connector()
    if settings.connector == "google":
        if settings.uses_default_hosts:
            raise ValueError("Google 模式請設定 SEO_PULSE_PRODUCTION_HOSTS 為正式網域，不能沿用 example.com。")
        # Optional [google] extra: import only when selected so fixture mode needs only mcp.
        from .google import GoogleGSCConnector, GoogleGA4Connector
        return GoogleGSCConnector(), GoogleGA4Connector()
    raise ValueError("SEO_PULSE_CONNECTOR must be fixture or google")
