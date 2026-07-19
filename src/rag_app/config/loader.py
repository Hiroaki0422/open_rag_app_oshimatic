"""Configuration composition and inspection entry point."""

import json

from .models import Settings


def load_settings() -> Settings:
    return Settings()


def inspect_config() -> None:
    settings = load_settings()
    print(json.dumps(settings.redacted_dict(), indent=2, sort_keys=True))


if __name__ == "__main__":
    inspect_config()
