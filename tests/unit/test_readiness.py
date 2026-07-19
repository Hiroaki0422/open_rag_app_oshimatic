from rag_app.application.readiness import ReadinessApplicationService


class Check:
    def __init__(self, name: str, ready: bool) -> None:
        self.name = name
        self.ready = ready

    def check(self) -> tuple[bool, str | None]:
        return self.ready, None if self.ready else "unavailable"


def test_readiness_reports_each_dependency() -> None:
    result = ReadinessApplicationService((Check("sqlite", True), Check("search", False))).check()
    assert result.ready is False
    assert result.dependencies["sqlite"].ready is True
    assert result.dependencies["search"].detail == "unavailable"


class ThrowingCheck:
    name = "throwing"

    def check(self) -> tuple[bool, str | None]:
        raise RuntimeError("sensitive dependency detail")


def test_readiness_isolates_throwing_dependencies(caplog) -> None:  # type: ignore[no-untyped-def]
    result = ReadinessApplicationService((Check("sqlite", True), ThrowingCheck())).check()
    assert result.ready is False
    assert result.dependencies["sqlite"].ready is True
    assert result.dependencies["throwing"].ready is False
    assert result.dependencies["throwing"].detail == "RuntimeError: dependency check failed"
    assert "sensitive dependency detail" not in caplog.text
