import json
from pathlib import Path

import pytest

from gamebox.common.logging import JsonlLogger


def test_jsonl_common_fields_and_rotation(tmp_path: Path) -> None:
    path = tmp_path / "core.jsonl"
    log = JsonlLogger(path, component="core", max_bytes=100, backup_count=2)
    log.log("one", session_id="s1", turn_id="t1", call_id="c1", text="привет")
    log.log("two", value=2)
    backup = path.with_name("core.jsonl.1")
    assert backup.exists()
    first = json.loads(backup.read_text(encoding="utf-8"))
    current = json.loads(path.read_text(encoding="utf-8"))
    assert first["text"] == "привет"
    assert current["event"] == "two"
    assert {"ts", "component", "session_id", "turn_id", "call_id"} <= first.keys()


def test_invalid_payload_does_not_write(tmp_path: Path) -> None:
    path = tmp_path / "core.jsonl"
    log = JsonlLogger(path, component="core")
    with pytest.raises(TypeError):
        log.log("bad", value=object())
    assert not path.exists()
