"""Неизменяемые события §5.3 и однопетлевая asyncio-шина."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from concurrent.futures import Future
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TypeVar

JSONValue = object  # Полезная нагрузка проверяется схемой протокола в блоке 7.
Event = object
Handler = Callable[[object], Awaitable[None]]
E = TypeVar("E")
_LOG = logging.getLogger(__name__)


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_freeze(item) for item in value)
    return value


@dataclass(frozen=True, slots=True)
class UiAction:
    name: str
    payload: Mapping[str, JSONValue] = field(default_factory=lambda: MappingProxyType({}))
    rev: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", _freeze(self.payload))


@dataclass(frozen=True, slots=True)
class SpeechStart:
    duration_s: float = 0.0
    level_dbfs: float = -120.0


@dataclass(frozen=True, slots=True)
class SpeechEnd:
    duration_s: float
    level_dbfs: float
    pcm: bytes = b""


@dataclass(frozen=True, slots=True)
class Utterance:
    text: str
    norm: str
    lemmas: tuple[str, ...] = ()
    confidence: float | None = None


@dataclass(frozen=True, slots=True)
class SayStarted:
    say_id: str


@dataclass(frozen=True, slots=True)
class SayFinished:
    say_id: str
    interrupted: bool = False


@dataclass(frozen=True, slots=True)
class Timeout:
    timer_id: str


@dataclass(frozen=True, slots=True)
class PackEvent:
    kind: str
    pack_id: str


class EventBus:
    """Подписки и обработчики живут в одной петле; потоки используют publish_threadsafe."""

    def __init__(self, maxsize: int = 1024) -> None:
        self._queue: asyncio.Queue[object | None] = asyncio.Queue(maxsize=maxsize)
        self._handlers: dict[type, list[Handler]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stopping = False

    def subscribe(
        self, event_type: type[E], handler: Callable[[E], Awaitable[None]]
    ) -> Callable[[], None]:
        handlers = self._handlers.setdefault(event_type, [])
        handlers.append(handler)  # type: ignore[arg-type]

        def unsubscribe() -> None:
            if handler in handlers:
                handlers.remove(handler)

        return unsubscribe

    async def publish(self, event: Event) -> None:
        if self._stopping:
            raise RuntimeError("Шина остановлена")
        await self._queue.put(event)

    def publish_threadsafe(self, event: Event) -> Future[None]:
        """Возвращает Future: worker может дождаться результата и получить QueueFull."""
        if self._loop is None or self._loop.is_closed():
            raise RuntimeError("Шина не запущена")
        result: Future[None] = Future()
        self._loop.call_soon_threadsafe(self._enqueue, event, result)
        return result

    def _enqueue(self, event: Event, result: Future[None]) -> None:
        try:
            if self._stopping:
                raise RuntimeError("Шина остановлена")
            self._queue.put_nowait(event)
        except Exception as exc:
            result.set_exception(exc)
        else:
            result.set_result(None)

    async def run(self) -> None:
        self._loop = asyncio.get_running_loop()
        try:
            while True:
                event = await self._queue.get()
                try:
                    if event is None:
                        return
                    for handler in tuple(self._handlers.get(type(event), ())):
                        try:
                            await handler(event)
                        except Exception:
                            _LOG.exception("Ошибка подписчика события %s", type(event).__name__)
                finally:
                    self._queue.task_done()
        finally:
            self._loop = None

    async def join(self) -> None:
        await self._queue.join()

    def stop(self) -> None:
        self._stopping = True
        self._queue.put_nowait(None)
