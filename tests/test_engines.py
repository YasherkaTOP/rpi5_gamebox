import math

import pytest

from gamebox.common.engines import (
    AsrEngine,
    Embedder,
    FakeAsr,
    FakeEmbedder,
    FakeLlm,
    FakeTts,
    FakeVad,
    LlmBackend,
    Message,
    TtsEngine,
    Vad,
)


def test_fake_asr_and_tts() -> None:
    asr = FakeAsr(("да", "нет"))
    assert isinstance(asr, AsrEngine)
    assert asr.transcribe(b"").text == "да"
    assert asr.transcribe(b"").text == "нет"
    tts = FakeTts()
    assert isinstance(tts, TtsEngine)
    audio = tts.synthesize("привет", "host", 1.0)
    assert len(audio) % 2 == 0
    assert audio == b"\x00\x00" * (len(audio) // 2)


async def test_fake_llm_script_and_stop() -> None:
    llm = FakeLlm(("один два три", "готово"))
    assert isinstance(llm, LlmBackend)
    messages: list[Message] = [{"role": "user", "content": "тест"}]
    tokens = [token async for token in llm.generate(messages, 2, 0.0, 1)]
    assert tokens == ["один ", "два "]
    tokens = [token async for token in llm.generate(messages, 10, 0.0, 1, stop=(" ",))]
    assert tokens == ["готово"]


def test_fake_embedder_and_vad() -> None:
    embedder = FakeEmbedder(16)
    assert isinstance(embedder, Embedder)
    a, b = embedder.embed(["Привет", "привет"])
    assert a == b
    assert math.isclose(math.sqrt(sum(x * x for x in a)), 1.0)
    vad = FakeVad()
    assert isinstance(vad, Vad)
    assert vad.frame_prob(b"\x00\x00" * 16) == 0.0
    assert vad.frame_prob(b"\x00\x40" * 16) == 1.0
    with pytest.raises(ValueError):
        vad.frame_prob(b"\x00")
