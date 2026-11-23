import asyncio
from dataclasses import FrozenInstanceError

import pytest

from gamebox.common.events import EventBus, Timeout, UiAction, Utterance


def test_events_are_frozen() -> None:
    event = UiAction("tap", {"cell": "B5"}, rev=1)
    with pytest.raises(FrozenInstanceError):
        event.name = "other"  # type: ignore[misc]


async def test_bus_dispatch_and_threadsafe_publish() -> None:
    bus = EventBus()
    received: list[object] = []

    async def handle(event: Utterance) -> None:
        received.append(event)

    unsubscribe = bus.subscribe(Utterance, handle)
    task = asyncio.create_task(bus.run())
    await asyncio.sleep(0)
    event = Utterance("да", "да", ("да",), 1.0)
    await asyncio.to_thread(bus.publish_threadsafe(event).result, 2)
    await bus.publish(Timeout("ignored"))
    await bus.join()
    assert received == [event]
    unsubscribe()
    bus.stop()
    await task


async def test_subscriber_error_does_not_stop_bus() -> None:
    bus = EventBus()
    received: list[str] = []

    async def bad(event: UiAction) -> None:
        raise RuntimeError("boom")

    async def good(event: UiAction) -> None:
        received.append(event.name)

    bus.subscribe(UiAction, bad)
    bus.subscribe(UiAction, good)
    task = asyncio.create_task(bus.run())
    await asyncio.sleep(0)
    await bus.publish(UiAction("tap"))
    await bus.join()
    assert received == ["tap"]
    bus.stop()
    await task


def test_ui_action_payload_is_deeply_immutable() -> None:
    event = UiAction("tap", {"cells": ["B5"], "meta": {"ok": True}})
    with pytest.raises(TypeError):
        event.payload["cells"] = ()  # type: ignore[index]
    cells = event.payload["cells"]
    assert isinstance(cells, tuple)
