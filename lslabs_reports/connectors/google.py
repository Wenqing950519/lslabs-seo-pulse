from .base import GSCConnector, GA4Connector

# TODO: implement user-owned OAuth with ONLY these read-only scopes:
# https://www.googleapis.com/auth/webmasters.readonly
# https://www.googleapis.com/auth/analytics.readonly
# No OAuth or network implementation exists in this skeleton.


class GoogleGSCConnector(GSCConnector):
    def list_sites(self):
        raise NotImplementedError("TODO: Google OAuth webmasters.readonly")

    def query(self, start_date, end_date, dimensions, filters=None):
        raise NotImplementedError("TODO: Google OAuth webmasters.readonly")


class GoogleGA4Connector(GA4Connector):
    def report(self, start_date, end_date):
        raise NotImplementedError("TODO: Google OAuth analytics.readonly")
