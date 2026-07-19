"""Bounded OpenSearch readiness adapter."""

from __future__ import annotations

import json
import urllib.error
import urllib.request


class OpenSearchHealth:
    name = "opensearch"

    def __init__(self, url: str, timeout_seconds: float) -> None:
        self.url = url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def check(self) -> tuple[bool, str | None]:
        try:
            with urllib.request.urlopen(
                f"{self.url}/_cluster/health", timeout=self.timeout_seconds
            ) as response:
                payload = json.load(response)
            status = payload.get("status")
            if status not in {"green", "yellow"}:
                return False, f"cluster status is {status or 'unknown'}"
            return True, None
        except (OSError, ValueError, urllib.error.URLError) as exc:
            return False, str(exc)
