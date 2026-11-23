"""Типизированный TOML-конфиг. Источник JSON Schema — модели этого модуля."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Profile = Literal["device", "dev"]
EngineName = Literal["fake"]  # Реальные имена добавляются вместе с адаптерами в блоке 3.


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, allow_inf_nan=False)


class Paths(StrictModel):
    """Все данные §4.1 выводятся из одного корня; относительные пути решает load_config."""

    root: Path = Path("./var")
    runtime: Path = Path("./var/run")

    @field_validator("root", "runtime", mode="before")
    @classmethod
    def path_from_toml(cls, value: object) -> object:
        return Path(value) if isinstance(value, str) else value

    @property
    def games(self) -> Path:
        return self.root / "games"

    @property
    def packs(self) -> Path:
        return self.root / "packs"

    @property
    def personas(self) -> Path:
        return self.root / "personas"

    @property
    def models(self) -> Path:
        return self.root / "models"

    @property
    def resources(self) -> Path:
        return self.root / "resources"

    @property
    def db(self) -> Path:
        return self.root / "db" / "gamebox.sqlite"

    @property
    def tts_cache(self) -> Path:
        return self.root / "tts_cache"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    @property
    def audio_debug(self) -> Path:
        return self.root / "audio_debug"

    @property
    def llm_socket(self) -> Path:
        return self.runtime / "llm.sock"

    def resolve(self, base: Path) -> Self:
        return type(self)(
            root=(base / self.root).resolve(),
            runtime=(base / self.runtime).resolve(),
        )

    def ensure_directories(self) -> None:
        for path in (
            self.root,
            self.runtime,
            self.games,
            self.packs,
            self.personas,
            self.models,
            self.resources,
            self.db.parent,
            self.tts_cache,
            self.logs,
            self.audio_debug,
        ):
            path.mkdir(parents=True, exist_ok=True)


class Engines(StrictModel):
    asr: EngineName = "fake"
    tts: EngineName = "fake"
    llm: EngineName = "fake"
    embedder: EngineName = "fake"
    vad: EngineName = "fake"


class Audio(StrictModel):
    input_device: str = "plughw:CARD=Device,DEV=0"
    output_device: str = "hdmi:CARD=vc4hdmi1,DEV=0"
    capture_sample_rate: int = Field(default=48000, gt=0)
    sample_rate: int = Field(default=16000, gt=0)
    channels: int = Field(default=1, ge=1, le=1)
    pre_roll_ms: int = Field(default=300, ge=0)
    volume: float = Field(default=0.6, ge=0.0, le=1.0)


class Vad(StrictModel):
    frame_ms: int = Field(default=32, gt=0)
    threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    min_speech_ms: int = Field(default=250, gt=0)
    silence_word_ms: int = Field(default=500, gt=0)
    silence_phrase_ms: int = Field(default=850, gt=0)
    silence_long_ms: int = Field(default=1200, gt=0)
    max_rejected: int = Field(default=3, gt=0)


class Asr(StrictModel):
    model: str = ""
    language: Literal["ru"] = "ru"


class Tts(StrictModel):
    voice: str = "irina"
    rate: float = Field(default=1.0, gt=0.0)
    cache_max_bytes: int = Field(default=2_000_000_000, ge=0)
    sentence_min_chars: int = Field(default=20, ge=0)


class Llm(StrictModel):
    model: str = ""
    context_tokens: int = Field(default=2048, gt=0)
    prompt_budget_tokens: int = Field(default=1000, gt=0)
    request_timeout_s: float = Field(default=30.0, gt=0.0)
    max_tokens: int = Field(default=40, gt=0)
    temperature: float = Field(default=0.0, ge=0.0)


class Ui(StrictModel):
    static_dir: Path = Path("ui/dist")

    @field_validator("static_dir", mode="before")
    @classmethod
    def path_from_toml(cls, value: object) -> object:
        return Path(value) if isinstance(value, str) else value

    width: int = Field(default=1024, gt=0)
    height: int = Field(default=600, gt=0)
    min_touch_px: int = Field(default=56, gt=0)
    min_text_px: int = Field(default=22, gt=0)


class Api(StrictModel):
    bind: str = "127.0.0.1"
    port: int = Field(default=8080, ge=1, le=65535)
    request_max_bytes: int = Field(default=100_000_000, gt=0)


class Logging(StrictModel):
    level: Literal["debug", "info", "warning", "error"] = "info"
    max_bytes: int = Field(default=10_000_000, gt=0)
    backup_count: int = Field(default=5, ge=0)


class Config(StrictModel):
    profile: Profile = "dev"
    engines: Engines = Field(default_factory=Engines)
    audio: Audio = Field(default_factory=Audio)
    vad: Vad = Field(default_factory=Vad)
    asr: Asr = Field(default_factory=Asr)
    tts: Tts = Field(default_factory=Tts)
    llm: Llm = Field(default_factory=Llm)
    paths: Paths = Field(default_factory=Paths)
    ui: Ui = Field(default_factory=Ui)
    api: Api = Field(default_factory=Api)
    logging: Logging = Field(default_factory=Logging)

    @model_validator(mode="before")
    @classmethod
    def profile_defaults(cls, value: object) -> object:
        if isinstance(value, dict) and "paths" not in value:
            data = dict(value)
            if data.get("profile", "dev") == "device":
                data["paths"] = {"root": "/var/lib/gamebox", "runtime": "/run/gamebox"}
            return data
        return value

    def resolve_paths(self, base: Path) -> Config:
        base = base.resolve()
        return self.model_copy(
            update={
                "paths": self.paths.resolve(base),
                "ui": self.ui.model_copy(
                    update={"static_dir": (base / self.ui.static_dir).resolve()}
                ),
            }
        )


def load_config(path: Path | None = None, *, profile: Profile | None = None) -> Config:
    """Читает TOML; относительные пути считаются от каталога файла (или cwd)."""
    data: dict[str, object] = {}
    base = Path.cwd()
    if path is not None:
        path = path.resolve()
        base = path.parent
        with path.open("rb") as stream:
            data = tomllib.load(stream)
    if profile is not None:
        data["profile"] = profile
        if "paths" not in data:
            data["paths"] = (
                {"root": "/var/lib/gamebox", "runtime": "/run/gamebox"}
                if profile == "device"
                else {"root": "./var", "runtime": "./var/run"}
            )
    return Config.model_validate(data).resolve_paths(base)
