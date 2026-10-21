from abc import ABC, abstractmethod


class GSCConnector(ABC):
    @abstractmethod
    def list_sites(self) -> list[dict]: ...

    @abstractmethod
    def query(self, start_date: str, end_date: str, dimensions: list[str],
              filters: dict | None = None) -> list[dict]: ...


class GA4Connector(ABC):
    @abstractmethod
    def report(self, start_date: str, end_date: str) -> list[dict]: ...

    def list_properties(self) -> list[dict]:
        raise NotImplementedError
