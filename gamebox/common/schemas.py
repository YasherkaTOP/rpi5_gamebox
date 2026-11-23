"""Генерация JSON Schema из общих моделей — единственный источник правды."""

from __future__ import annotations

from typing import Any

from gamebox.common.config import Config


def config_schema() -> dict[str, Any]:
    return Config.model_json_schema()
