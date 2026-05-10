"""Tests for VoiceTurnManager.speak_streaming and related paths.

Covers the speak_streaming method (play_streaming_tokens path) and
the wait_for_utterance / start_stt helpers.
"""
import asyncio
from collections.abc import AsyncIterator
from unittest.mock import MagicMock

import pytest

from daily.voice.barge_in import VoiceTurnManager


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeTTSStreaming:
    """Fake TTS that supports play_streaming_tokens."""

    def __init__(self, sleep_duration: float = 10.0) -> None:
        self._sleep_duration = sleep_duration
        self.tokens_received: list[str] = []

    async def play_streaming(self, text: str, stop_event: asyncio.Event) -> None:
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=self._sleep_duration)
        except asyncio.TimeoutError:
            pass

    async def play_streaming_tokens(
        self, token_stream: AsyncIterator[str], stop_event: asyncio.Event
    ) -> None:
        async for tok in token_stream:
            self.tokens_received.append(tok)
            if stop_event.is_set():
                break
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=self._sleep_duration)
        except asyncio.TimeoutError:
            pass


class _FakeTTSStreamingInstant:
    """Fake TTS that returns immediately from play_streaming_tokens."""

    def __init__(self) -> None:
        self.tokens_received: list[str] = []

    async def play_streaming(self, text: str, stop_event: asyncio.Event) -> None:
        pass

    async def play_streaming_tokens(
        self, token_stream: AsyncIterator[str], stop_event: asyncio.Event
    ) -> None:
        async for tok in token_stream:
            self.tokens_received.append(tok)


class _FakeSTT:
    """Minimal fake STT for barge-in tests."""

    def __init__(self) -> None:
        self.utterance_queue: asyncio.Queue[str] = asyncio.Queue()
        self._on_speech_started = None
        self._transcript_parts: list[str] = []
        self._has_speech_transcript: bool = False
        self.muted: bool = False

    async def start_listening(self, stop_event: asyncio.Event) -> None:
        await stop_event.wait()


async def _token_stream(*tokens: str) -> AsyncIterator[str]:
    for tok in tokens:
        yield tok


# ---------------------------------------------------------------------------
# speak_streaming tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_speak_streaming_returns_true_on_completion() -> None:
    """speak_streaming returns True when token stream completes without barge-in."""
    tts = _FakeTTSStreamingInstant()
    manager = VoiceTurnManager(tts=tts, stt=_FakeSTT())

    stream = _token_stream("Hello", " world")
    result = await manager.speak_streaming(stream)

    assert result is True


@pytest.mark.asyncio
async def test_speak_streaming_delivers_tokens_to_tts() -> None:
    """speak_streaming passes the full token stream through to TTS."""
    tts = _FakeTTSStreamingInstant()
    manager = VoiceTurnManager(tts=tts, stt=_FakeSTT())

    stream = _token_stream("foo", "bar", "baz")
    await manager.speak_streaming(stream)

    assert tts.tokens_received == ["foo", "bar", "baz"]


@pytest.mark.asyncio
async def test_speak_streaming_sets_tts_active_during_playback() -> None:
    """_tts_active is True while speak_streaming is running, False after."""
    active_during: list[bool] = []
    tts = _FakeTTSStreamingInstant()
    manager = VoiceTurnManager(tts=tts, stt=_FakeSTT())

    # Wrap to capture _tts_active mid-call
    original = tts.play_streaming_tokens

    async def capture(stream, stop_event):
        active_during.append(manager._tts_active)
        await original(stream, stop_event)

    tts.play_streaming_tokens = capture

    stream = _token_stream("test")
    await manager.speak_streaming(stream)

    assert active_during == [True], "_tts_active should be True during playback"
    assert manager._tts_active is False, "_tts_active should be False after completion"


@pytest.mark.asyncio
async def test_speak_streaming_returns_false_on_barge_in() -> None:
    """speak_streaming returns False when stop_event is set during playback."""
    tts = _FakeTTSStreaming(sleep_duration=10.0)
    manager = VoiceTurnManager(tts=tts, stt=_FakeSTT())

    async def empty_stream() -> AsyncIterator[str]:
        # Yield nothing — wait happens in play_streaming_tokens
        return
        yield  # noqa: unreachable — makes this a generator

    async def trigger_stop() -> None:
        await asyncio.sleep(0.05)
        manager._stop_event.set()

    asyncio.create_task(trigger_stop())
    result = await manager.speak_streaming(empty_stream())

    assert result is False


@pytest.mark.asyncio
async def test_speak_streaming_clears_stop_event_after_completion() -> None:
    """stop_event is cleared after speak_streaming completes."""
    tts = _FakeTTSStreamingInstant()
    manager = VoiceTurnManager(tts=tts, stt=_FakeSTT())

    stream = _token_stream("hi")
    await manager.speak_streaming(stream)

    assert not manager._stop_event.is_set()


@pytest.mark.asyncio
async def test_speak_streaming_restores_stt_muted_on_completion() -> None:
    """_stt.muted is False after speak_streaming finishes."""
    tts = _FakeTTSStreamingInstant()
    stt = _FakeSTT()
    manager = VoiceTurnManager(tts=tts, stt=stt)

    stream = _token_stream("hi")
    await manager.speak_streaming(stream)

    assert stt.muted is False


# ---------------------------------------------------------------------------
# wait_for_utterance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wait_for_utterance_returns_queued_text() -> None:
    """wait_for_utterance returns the next item from utterance_queue."""
    stt = _FakeSTT()
    manager = VoiceTurnManager(tts=_FakeTTSStreamingInstant(), stt=stt)

    await stt.utterance_queue.put("check my calendar")
    result = await manager.wait_for_utterance()

    assert result == "check my calendar"


@pytest.mark.asyncio
async def test_wait_for_utterance_blocks_until_available() -> None:
    """wait_for_utterance suspends until an item arrives in the queue."""
    stt = _FakeSTT()
    manager = VoiceTurnManager(tts=_FakeTTSStreamingInstant(), stt=stt)

    async def produce() -> None:
        await asyncio.sleep(0.05)
        await stt.utterance_queue.put("delayed utterance")

    asyncio.create_task(produce())
    result = await manager.wait_for_utterance()

    assert result == "delayed utterance"


# ---------------------------------------------------------------------------
# start_stt
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_stt_wires_callback() -> None:
    """start_stt sets _on_speech_started on the STT to the manager's handler."""
    stt = _FakeSTT()
    manager = VoiceTurnManager(tts=_FakeTTSStreamingInstant(), stt=stt)

    stop_event = asyncio.Event()
    task = asyncio.create_task(manager.start_stt(stop_event))
    await asyncio.sleep(0)  # yield to let start_stt run

    # Bound methods compare equal but are not the same object; check name and self
    assert stt._on_speech_started.__func__ is manager._on_speech_started.__func__

    stop_event.set()
    await task
