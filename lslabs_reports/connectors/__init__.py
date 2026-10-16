import os
from .fixture import FixtureGSCConnector, FixtureGA4Connector
from .google import GoogleGSCConnector, GoogleGA4Connector


def get_connectors():
    mode = os.getenv("LSLABS_CONNECTOR", "fixture")
    if mode == "fixture":
        return FixtureGSCConnector(), FixtureGA4Connector()
    if mode == "google":
        return GoogleGSCConnector(), GoogleGA4Connector()
    raise ValueError("LSLABS_CONNECTOR must be fixture or google")
