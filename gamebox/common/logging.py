"""JSONL-журнал с общими полями и ротацией. Долговечные таблицы появятся в блоке 8."""

from __future__ import annotations

import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

Level = Literal["debug", "info", "warning", "error"]


class JsonlLogger:
    def __init__(
        self,
        path: Path,
        *,
        component: str,
        max_bytes: int = 10_000_000,
        backup_count: int = 5,
    ) -> None:
        if max_bytes <= 0 or backup_count < 0:
            raise ValueError("max_bytes должен быть > 0, backup_count >= 0")
        self.path = path
        self.component = component
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self._lock = threading.RLock()

    def log(
        self,
        event: str,
        *,
        level: Level = "info",
        session_id: str | None = None,
        turn_id: str | None = None,
        call_id: str | None = None,
        **fields: object,
    ) -> None:
        record = {
            "ts": datetime.now(UTC).isoformat(),
            "component": self.component,
            "session_id": session_id,
            "turn_id": turn_id,
            "call_id": call_id,
            "event": event,
            "level": level,
            **fields,
        }
        line = json.dumps(record, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n"
        payload = line.encode("utf-8")
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists() and self.path.stat().st_size + len(payload) > self.max_bytes:
                self._rotate()
            with self.path.open("ab") as stream:
                stream.write(payload)
                stream.flush()

    def _rotate(self) -> None:
        if self.backup_count == 0:
            self.path.unlink(missing_ok=True)
            return
        oldest = self.path.with_name(f"{self.path.name}.{self.backup_count}")
        oldest.unlink(missing_ok=True)
        for index in range(self.backup_count - 1, 0, -1):
            source = self.path.with_name(f"{self.path.name}.{index}")
            if source.exists():
                os.replace(source, self.path.with_name(f"{self.path.name}.{index + 1}"))
        os.replace(self.path, self.path.with_name(f"{self.path.name}.1"))
