import os

import pytest

from rag_app.application.readiness import ReadinessApplicationService
from rag_app.infrastructure.opensearch.health import OpenSearchHealth

pytestmark = pytest.mark.integration


def test_live_opensearch_readiness() -> None:
    url = os.getenv("RAG_LIVE_OPENSEARCH_URL")
    if not url:
        pytest.skip("RAG_LIVE_OPENSEARCH_URL is not configured")
    result = ReadinessApplicationService((OpenSearchHealth(url, timeout_seconds=5),)).check()
    assert result.ready, result.dependencies["opensearch"].detail
