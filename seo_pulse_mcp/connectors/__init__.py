import os
from .fixture import FixtureGSCConnector, FixtureGA4Connector


def get_connectors():
    mode = os.getenv("SEO_PULSE_CONNECTOR", "fixture")
    if mode == "fixture":
        return FixtureGSCConnector(), FixtureGA4Connector()
    if mode == "google":
        # Optional [google] extra: import only when selected so fixture mode needs only mcp.
        from .google import GoogleGSCConnector, GoogleGA4Connector
        return GoogleGSCConnector(), GoogleGA4Connector()
    raise ValueError("SEO_PULSE_CONNECTOR must be fixture or google")
