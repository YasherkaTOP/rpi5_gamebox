"""Интерфейсы движков и детерминированные фейки. Реальные адаптеры — блок 3.

ASR/TTS/VAD/Embedder синхронные: сервисы ядра вызывают их через asyncio.to_thread.
LLM — асинхронный поток токенов. PCM везде: signed int16, little-endian, моно.
"""

from __future__ import annotations

import hashlib
import math
import re
import struct
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from itertools import cycle
from typing import Literal, Protocol, TypedDict, runtime_checkable

Pcm16 = bytes


class Message(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True, slots=True)
class AsrWord:
    text: str
    start_s: float
    end_s: float
    confidence: float | None = None


@dataclass(frozen=True, slots=True)
class AsrResult:
    text: str
    confidence: float | None = None
    words: tuple[AsrWord, ...] | None = None


@dataclass(frozen=True, slots=True)
class MatchResult:
    candidate: str
    index: int
    score: float


@runtime_checkable
class AsrEngine(Protocol):
    def transcribe(self, pcm_16k: Pcm16) -> AsrResult: ...


@runtime_checkable
class TtsEngine(Protocol):
    def synthesize(self, text: str, voice: str, rate: float = 1.0) -> Pcm16: ...


@runtime_checkable
class LlmBackend(Protocol):
    def generate(
        self,
        messages: Sequence[Message],
        max_tokens: int,
        temperature: float,
        seed: int | None,
        stop: Sequence[str] = (),
    ) -> AsyncIterator[str]: ...


@runtime_checkable
class Embedder(Protocol):
    def embed(self, texts: Sequence[str]) -> list[tuple[float, ...]]: ...


@runtime_checkable
class Vad(Protocol):
    def frame_prob(self, frame: Pcm16) -> float: ...


class FakeAsr:
    def __init__(self, transcripts: Sequence[str] = ("да",), confidence: float = 1.0) -> None:
        if not transcripts:
            raise ValueError("Нужна хотя бы одна строка сценария")
        self._transcripts = cycle(transcripts)
        self._confidence = confidence

    def transcribe(self, pcm_16k: Pcm16) -> AsrResult:
        return AsrResult(next(self._transcripts), self._confidence, None)


class FakeTts:
    def __init__(
        self, sample_rate: int = 16000, seconds_per_char: float = 0.02, min_duration_s: float = 0.1
    ) -> None:
        self.sample_rate = sample_rate
        self.seconds_per_char = seconds_per_char
        self.min_duration_s = min_duration_s

    def synthesize(self, text: str, voice: str, rate: float = 1.0) -> Pcm16:
        if rate <= 0:
            raise ValueError("rate должен быть > 0")
        duration = max(self.min_duration_s, len(text) * self.seconds_per_char) / rate
        return b"\x00\x00" * int(duration * self.sample_rate)


class FakeLlm:
    """Сценарий ответов по кругу; temperature/seed не влияют на детерминированный вывод."""

    def __init__(self, responses: Sequence[str] = ("готово",)) -> None:
        if not responses:
            raise ValueError("Нужен хотя бы один ответ сценария")
        self._responses = cycle(responses)

    async def generate(
        self,
        messages: Sequence[Message],
        max_tokens: int,
        temperature: float,
        seed: int | None,
        stop: Sequence[str] = (),
    ) -> AsyncIterator[str]:
        response = next(self._responses)
        for marker in stop:
            index = response.find(marker)
            if index >= 0:
                response = response[:index]
        for token in re.findall(r"\S+\s*", response)[:max_tokens]:
            yield token


class FakeEmbedder:
    def __init__(self, dimensions: int = 64) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions должен быть > 0")
        self.dimensions = dimensions

    def embed(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        return [self._one(text) for text in texts]

    def _one(self, text: str) -> tuple[float, ...]:
        values: list[float] = []
        counter = 0
        while len(values) < self.dimensions:
            digest = hashlib.sha256(f"{text.lower()}:{counter}".encode()).digest()
            values.extend((byte - 127.5) / 127.5 for byte in digest)
            counter += 1
        values = values[: self.dimensions]
        norm = math.sqrt(sum(value * value for value in values))
        return tuple(value / norm for value in values)


class FakeVad:
    """Энергетический фейк, не Silero: ненулевой сигнал выше порога считается речью."""

    def __init__(self, amplitude_threshold: float = 0.01) -> None:
        self.amplitude_threshold = amplitude_threshold

    def frame_prob(self, frame: Pcm16) -> float:
        if len(frame) % 2:
            raise ValueError("PCM должен содержать целые int16")
        if not frame:
            return 0.0
        samples = struct.unpack(f"<{len(frame) // 2}h", frame)
        rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples)) / 32768.0
        return 1.0 if rms >= self.amplitude_threshold else 0.0
