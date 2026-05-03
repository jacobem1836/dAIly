"""Tests for daily.worker.voice_pipeline — DailyAgentLLM and build_voice_pipeline.

Tests focus on what we own:
1. DailyAgentLLM correctly extracts the last user message from ChatContext.
2. build_voice_pipeline forwards the right arguments to the LiveKit plugin constructors.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_chat_ctx(*role_content_pairs):
    """Build a minimal fake ChatContext with messages."""
    messages = [
        SimpleNamespace(role=role, content=content)
        for role, content in role_content_pairs
    ]
    return SimpleNamespace(messages=messages)


# ---------------------------------------------------------------------------
# Test 1: DailyAgentLLM extracts the last user message
# ---------------------------------------------------------------------------
# The LLMStream constructor creates asyncio tasks, so tests that call
# DailyAgentLLM.chat() must run inside an event loop. We mock _DailyLLMStream
# to capture user_msg without triggering the real LLMStream init tasks.


def _make_capturing_stream_class():
    """Return a fake _DailyLLMStream that captures user_msg and doesn't start tasks."""
    class CapturingStream:
        def __init__(self, llm, *, chat_ctx, fnc_ctx, conn_options, bridge, user_msg):
            self._user_msg = user_msg
    return CapturingStream


@pytest.mark.asyncio
async def test_chat_extracts_last_user_message():
    """DailyAgentLLM.chat() extracts the most recent user-role message."""
    from daily.worker import voice_pipeline
    from daily.worker.voice_pipeline import DailyAgentLLM

    bridge = MagicMock()
    llm = DailyAgentLLM(bridge)

    # Chat context: system, user="hello", assistant, user="what's first?"
    chat_ctx = _make_chat_ctx(
        ("system", "You are a helpful assistant."),
        ("user", "hello"),
        ("assistant", "Hi there!"),
        ("user", "what's first?"),
    )

    with patch.object(voice_pipeline, "_DailyLLMStream", _make_capturing_stream_class()):
        stream = llm.chat(chat_ctx=chat_ctx)

    assert stream._user_msg == "what's first?"


@pytest.mark.asyncio
async def test_chat_extracts_only_user_message_when_single():
    """DailyAgentLLM.chat() works when there is a single user message."""
    from daily.worker import voice_pipeline
    from daily.worker.voice_pipeline import DailyAgentLLM

    bridge = MagicMock()
    llm = DailyAgentLLM(bridge)

    chat_ctx = _make_chat_ctx(("user", "hello"))

    with patch.object(voice_pipeline, "_DailyLLMStream", _make_capturing_stream_class()):
        stream = llm.chat(chat_ctx=chat_ctx)

    assert stream._user_msg == "hello"


@pytest.mark.asyncio
async def test_chat_returns_empty_string_when_no_user_message():
    """DailyAgentLLM.chat() returns empty string when no user message exists."""
    from daily.worker import voice_pipeline
    from daily.worker.voice_pipeline import DailyAgentLLM

    bridge = MagicMock()
    llm = DailyAgentLLM(bridge)

    chat_ctx = _make_chat_ctx(("system", "You are dAIly."))

    with patch.object(voice_pipeline, "_DailyLLMStream", _make_capturing_stream_class()):
        stream = llm.chat(chat_ctx=chat_ctx)

    assert stream._user_msg == ""


# ---------------------------------------------------------------------------
# Test 2: build_voice_pipeline wires all four components
# ---------------------------------------------------------------------------


def test_build_voice_pipeline_returns_voice_pipeline_agent():
    """build_voice_pipeline wires STT, TTS, VAD, and LLM to VoicePipelineAgent."""
    from daily.worker.voice_pipeline import DailyAgentLLM, build_voice_pipeline

    captured: dict = {}

    class FakeSTT:
        def __init__(self, **kwargs):
            captured["stt_kwargs"] = kwargs

    class FakeTTS:
        def __init__(self, **kwargs):
            captured["tts_kwargs"] = kwargs

    class FakeVAD:
        pass

    fake_vad_instance = FakeVAD()

    class FakeVoicePipelineAgent:
        def __init__(self, **kwargs):
            captured["agent_kwargs"] = kwargs

    bridge = MagicMock()
    settings = SimpleNamespace(
        deepgram_api_key="dg-test-key",
        cartesia_api_key="ca-test-key",
    )

    with (
        patch("daily.worker.voice_pipeline.deepgram.STT", FakeSTT),
        patch("daily.worker.voice_pipeline.cartesia.TTS", FakeTTS),
        patch("daily.worker.voice_pipeline.silero.VAD.load", return_value=fake_vad_instance),
        patch("daily.worker.voice_pipeline.VoicePipelineAgent", FakeVoicePipelineAgent),
    ):
        build_voice_pipeline(bridge, settings)

    # STT wired with nova-3 and API key
    assert captured["stt_kwargs"]["model"] == "nova-3"
    assert captured["stt_kwargs"]["api_key"] == "dg-test-key"

    # TTS wired with the correct API key
    assert captured["tts_kwargs"]["api_key"] == "ca-test-key"

    # LLM is a DailyAgentLLM wrapping the bridge
    assert isinstance(captured["agent_kwargs"]["llm"], DailyAgentLLM)

    # VAD is the silero instance
    assert captured["agent_kwargs"]["vad"] is fake_vad_instance
