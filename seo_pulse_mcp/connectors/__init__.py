from ..rules import RULES
from ..settings import load_settings
from .fixture import FixtureGSCConnector, FixtureGA4Connector


def get_connectors(settings=None, *, site_url=None, property_id=None, production_hosts=None):
    """site_url/property_id/production_hosts are per-request overrides for the Google
    connectors (see seo_pulse_mcp.resources for how tools resolve them); fixture mode
    ignores all three."""
    settings = settings or load_settings()
    if settings.connector == "fixture":
        return FixtureGSCConnector(), FixtureGA4Connector()
    if settings.connector == "google":
        blocked = (list(production_hosts) == RULES['production_hosts'] if production_hosts is not None
                   else settings.uses_default_hosts)
        if blocked:
            raise ValueError("Google 模式請設定 SEO_PULSE_PRODUCTION_HOSTS 為正式網域，不能沿用 example.com。")
        # Optional [google] extra: import only when selected so fixture mode needs only mcp.
        from .google import GoogleGSCConnector, GoogleGA4Connector
        return GoogleGSCConnector(site_url=site_url), GoogleGA4Connector(property_id=property_id)
    raise ValueError("SEO_PULSE_CONNECTOR must be fixture or google")
