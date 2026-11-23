from pathlib import Path

import pytest

from gamebox.common.config import Config
from gamebox.devtools.cli import run_smoke


async def test_smoke_uses_only_dev_paths(tmp_path: Path) -> None:
    config = Config(paths={"root": tmp_path / "var", "runtime": tmp_path / "run"})  # type: ignore[arg-type]
    result = await run_smoke(config)
    assert result["events"] == 1
    assert result["embedding_dimensions"] == 64
    assert (tmp_path / "var" / "logs" / "smoke.jsonl").exists()


def test_config_validate_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from gamebox.devtools.cli import main

    path = tmp_path / "config.toml"
    path.write_text('profile = "dev"\n', encoding="utf-8")
    main(["config", "validate", str(path)])
    assert '"profile": "dev"' in capsys.readouterr().out
