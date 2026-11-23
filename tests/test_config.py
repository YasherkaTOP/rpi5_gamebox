from pathlib import Path

import pytest
from pydantic import ValidationError

from gamebox.common.config import Config, load_config


def test_dev_defaults_and_relative_paths(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('profile = "dev"\n[paths]\nroot = "data"\nruntime = "run"\n', encoding="utf-8")
    config = load_config(path)
    assert config.paths.root == tmp_path / "data"
    assert config.paths.db == tmp_path / "data" / "db" / "gamebox.sqlite"
    assert config.paths.llm_socket == tmp_path / "run" / "llm.sock"
    assert config.audio.input_device == "plughw:CARD=Device,DEV=0"
    assert config.audio.output_device == "hdmi:CARD=vc4hdmi1,DEV=0"
    assert config.audio.capture_sample_rate == 48000
    assert config.audio.sample_rate == 16000


def test_device_profile_defaults() -> None:
    config = Config(profile="device")
    assert config.paths.root == Path("/var/lib/gamebox")
    assert config.paths.runtime == Path("/run/gamebox")


def test_unknown_key_and_bad_threshold_rejected() -> None:
    with pytest.raises(ValidationError):
        Config.model_validate({"unknown": 1})
    with pytest.raises(ValidationError):
        Config.model_validate({"vad": {"threshold": 2}})


def test_schema_is_frozen() -> None:
    config = Config()
    with pytest.raises(ValidationError):
        config.profile = "device"  # type: ignore[misc]
