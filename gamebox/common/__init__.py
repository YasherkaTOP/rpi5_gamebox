"""Общие контракты платформы. Не импортирует адаптеры реальных движков."""

from gamebox.common.config import Config, Paths, Profile, load_config
from gamebox.common.events import (
    Event,
    EventBus,
    PackEvent,
    SayFinished,
    SayStarted,
    SpeechEnd,
    SpeechStart,
    Timeout,
    UiAction,
    Utterance,
)
from gamebox.common.logging import JsonlLogger

__all__ = [
    "Config",
    "Event",
    "EventBus",
    "JsonlLogger",
    "PackEvent",
    "Paths",
    "Profile",
    "SayFinished",
    "SayStarted",
    "SpeechEnd",
    "SpeechStart",
    "Timeout",
    "UiAction",
    "Utterance",
    "load_config",
]
