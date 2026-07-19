import json

from rag_app.infrastructure.opensearch.health import OpenSearchHealth


class Response:
    def __init__(self, payload: dict[str, str]) -> None:
        self.payload = payload

    def __enter__(self) -> "Response":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode()


def test_opensearch_health_accepts_yellow_cluster(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda *_args, **_kwargs: Response({"status": "yellow"})
    )
    assert OpenSearchHealth("http://search:9200", 1).check() == (True, None)


def test_opensearch_health_reports_connection_failure(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def fail(*_args: object, **_kwargs: object) -> None:
        raise OSError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", fail)
    ready, detail = OpenSearchHealth("http://search:9200", 1).check()
    assert ready is False
    assert detail == "connection refused"
