"""CLI блока 2: проверка конфига и детерминированная smoke-проверка фундамента."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from gamebox import __version__
from gamebox.common.config import Config, Profile, load_config
from gamebox.common.engines import FakeAsr, FakeEmbedder, FakeLlm, FakeTts, FakeVad, Message
from gamebox.common.events import EventBus, Utterance
from gamebox.common.logging import JsonlLogger
from gamebox.common.text import lemmatize, normalize, number_to_words


async def run_smoke(config: Config) -> dict[str, object]:
    config.paths.ensure_directories()
    log = JsonlLogger(
        config.paths.logs / "smoke.jsonl",
        component="smoke",
        max_bytes=config.logging.max_bytes,
        backup_count=config.logging.backup_count,
    )
    bus = EventBus()
    received: list[Utterance] = []

    async def receive(event: Utterance) -> None:
        received.append(event)

    bus.subscribe(Utterance, receive)
    task = asyncio.create_task(bus.run())
    await asyncio.sleep(0)
    asr = FakeAsr(("Привет, ведущий!",))
    result = await asyncio.to_thread(asr.transcribe, b"\x00\x00" * 160)
    event = Utterance(
        result.text, normalize(result.text), lemmatize(result.text), result.confidence
    )
    await asyncio.to_thread(bus.publish_threadsafe(event).result, 2)
    await bus.join()
    bus.stop()
    await task
    messages: list[Message] = [{"role": "user", "content": result.text}]
    tokens = [token async for token in FakeLlm(("готов",)).generate(messages, 5, 0.0, 1)]
    audio = FakeTts().synthesize(" ".join(tokens), "host", config.tts.rate)
    vector = FakeEmbedder().embed([result.text])[0]
    vad = FakeVad().frame_prob(audio)
    summary = {
        "profile": config.profile,
        "version": __version__,
        "events": len(received),
        "asr": result.text,
        "lemmas": event.lemmas,
        "llm_tokens": tokens,
        "tts_bytes": len(audio),
        "embedding_dimensions": len(vector),
        "vad": vad,
        "number_example": number_to_words(21),
        "log": str(config.paths.logs / "smoke.jsonl"),
    }
    log.log("smoke.finished", result=summary)
    return summary


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="gamebox")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    config_parser = sub.add_parser("config")
    config_sub = config_parser.add_subparsers(dest="config_command", required=True)
    validate = config_sub.add_parser("validate")
    validate.add_argument("path", type=Path, nargs="?")
    validate.add_argument("--profile", choices=("device", "dev"))
    config_sub.add_parser("schema")
    smoke = sub.add_parser("smoke")
    smoke.add_argument("--config", type=Path)
    smoke.add_argument("--profile", choices=("device", "dev"))
    args = parser.parse_args(argv)
    if args.command == "config" and args.config_command == "schema":
        from gamebox.common.schemas import config_schema

        print(json.dumps(config_schema(), ensure_ascii=False, indent=2))
        return
    profile: Profile | None = args.profile
    config_path = args.path if args.command == "config" else args.config
    config = load_config(config_path, profile=profile)
    if args.command == "config":
        print(config.model_dump_json(indent=2))
    else:
        print(json.dumps(asyncio.run(run_smoke(config)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
