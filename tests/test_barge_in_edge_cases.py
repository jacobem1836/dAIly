"""Edge-case tests for VoiceTurnManager — covers previously-uncovered branches.

Targets barge_in.py lines:
  79   – _unmute_after_delay completes normally (sleep elapses without cancel)
  106  – _on_speech_started cancels a prior pending barge-in timer
  133-134 – _commit_barge_in_after_window returns early on CancelledError
  188  – speak() cancels a prior barge-in timer at entry
  243  – speak_streaming() cancels a prior barge-in timer at entry
  260-264 – speak_streaming CancelledError outer cancel path
  311  – stop() cancels a running barge-in timer
  328-332 – stop() cancels a running stt_task
"""
import asyncio
from collections.abc import AsyncIterator

import pytest

from daily.voice.barge_in import VoiceTurnManager


# ---------------------------------------------------------------------------
# Shared fakes (reuse pattern from test_voice_barge_in.py)
# ---------------------------------------------------------------------------


class _FakeTTSInstant:
    async def play_streaming(self, text: str, stop_event: asyncio.Event) -> None:
        pass

    async def play_streaming_tokens(
        self, token_stream: AsyncIterator[str], stop_event: asyncio.Event
    ) -> None:
        async for _ in token_stream:
            pass


class _FakeTTSSlow:
    """TTS that hangs until stop_event is set or cancelled."""

    async def play_streaming(self, text: str, stop_event: asyncio.Event) -> None:
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=30.0)
        except asyncio.TimeoutError:
            pass

    async def play_streaming_tokens(
        self, token_stream: AsyncIterator[str], stop_event: asyncio.Event
    ) -> None:
        async for _ in token_stream:
            pass
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=30.0)
        except asyncio.TimeoutError:
            pass


class _FakeSTT:
    def __init__(self) -> None:
        self.utterance_queue: asyncio.Queue[str] = asyncio.Queue()
        self._on_speech_started = None
        self._transcript_parts: list[str] = []
        self._has_speech_transcript: bool = False
        self.muted: bool = False

    async def start_listening(self, stop_event: asyncio.Event) -> None:
        await stop_event.wait()


async def _empty_stream() -> AsyncIterator[str]:
    return
    yield  # make it a generator


def _make_manager(tts=None, stt=None) -> VoiceTurnManager:
    return VoiceTurnManager(tts=tts or _FakeTTSInstant(), stt=stt or _FakeSTT())


# ---------------------------------------------------------------------------
# Line 79: _unmute_after_delay completes normally
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unmute_after_delay_completes_normally() -> None:
    """_unmute_after_delay unmutes STT after 0.15s without cancellation."""
    stt = _FakeSTT()
    manager = _make_manager(stt=stt)

    # Run the coroutine directly — should complete without CancelledError
    stt.muted = True
    task = asyncio.create_task(manager._unmute_after_delay())
    await task  # completes after 0.15s sleep
    assert stt.muted is False  # line 79 covered


# ---------------------------------------------------------------------------
# Line 106: _on_speech_started cancels prior pending timer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_speech_started_cancels_prior_timer() -> None:
    """_on_speech_started cancels a previously-running barge-in timer."""
    manager = _make_manager()

    # Create a long-running fake timer task
    async def _long_sleep():
        await asyncio.sleep(30.0)

    prior_task = asyncio.create_task(_long_sleep())
    manager._barge_in_timer_task = prior_task

    # Fire _on_speech_started — should cancel the prior task (line 106)
    manager._on_speech_started()
    await asyncio.sleep(0)  # yield to let cancellation propagate

    assert prior_task.cancelled()


# ---------------------------------------------------------------------------
# Lines 133-134: _commit_barge_in_after_window returns early on cancel
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_commit_barge_in_returns_on_cancel() -> None:
    """Cancelling _commit_barge_in_after_window causes early return (lines 133-134)."""
    manager = _make_manager()

    task = asyncio.create_task(manager._commit_barge_in_after_window())
    await asyncio.sleep(0)  # let the task start and enter sleep
    task.cancel()
    await asyncio.sleep(0)  # let cancellation propagate

    assert task.cancelled() or task.done()
    # stop_event must NOT have been set since the timer was cancelled
    assert not manager._stop_event.is_set()


# ---------------------------------------------------------------------------
# Line 188: speak() cancels a prior barge-in timer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_speak_cancels_prior_barge_in_timer() -> None:
    """speak() cancels a running barge-in timer left from a prior turn (line 188)."""
    manager = _make_manager()

    # Simulate a prior pending timer
    async def _long_sleep():
        await asyncio.sleep(30.0)

    prior_task = asyncio.create_task(_long_sleep())
    manager._barge_in_timer_task = prior_task

    # speak() should cancel the prior timer at entry
    await manager.speak("Hello world")
    await asyncio.sleep(0)

    assert prior_task.cancelled()


# ---------------------------------------------------------------------------
# Line 243: speak_streaming() cancels a prior barge-in timer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_speak_streaming_cancels_prior_barge_in_timer() -> None:
    """speak_streaming() cancels a running barge-in timer at entry (line 243)."""
    manager = _make_manager()

    async def _long_sleep():
        await asyncio.sleep(30.0)

    prior_task = asyncio.create_task(_long_sleep())
    manager._barge_in_timer_task = prior_task

    async def _stream():
        yield "hello"

    await manager.speak_streaming(_stream())
    await asyncio.sleep(0)

    assert prior_task.cancelled()


# ---------------------------------------------------------------------------
# Lines 260-264: speak_streaming CancelledError path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_speak_streaming_handles_outer_cancellation() -> None:
    """Cancelling the speak_streaming task itself triggers the CancelledError path."""
    stt = _FakeSTT()
    tts = _FakeTTSSlow()
    manager = _make_manager(tts=tts, stt=stt)

    # Run speak_streaming with an empty stream — TTS will hang
    task = asyncio.create_task(manager.speak_streaming(_empty_stream()))
    await asyncio.sleep(0.05)  # let it start and block in TTS

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    # After cancellation, state must be cleaned up
    assert manager._tts_active is False
    assert stt.muted is False


# ---------------------------------------------------------------------------
# Line 311: stop() cancels a running barge-in timer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stop_cancels_barge_in_timer() -> None:
    """stop() cancels a pending barge-in timer (line 311)."""
    manager = _make_manager()

    async def _long_sleep():
        await asyncio.sleep(30.0)

    timer_task = asyncio.create_task(_long_sleep())
    manager._barge_in_timer_task = timer_task

    await manager.stop()
    await asyncio.sleep(0)

    assert timer_task.cancelled()
    assert manager._barge_in_timer_task is None


# ---------------------------------------------------------------------------
# Lines 328-332: stop() cancels a running stt_task
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stop_cancels_stt_task() -> None:
    """stop() cancels the STT listener task (lines 328-332)."""
    stt = _FakeSTT()
    manager = _make_manager(stt=stt)

    listen_stop = asyncio.Event()
    await manager.start_stt(listen_stop)

    assert manager._stt_task is not None
    assert not manager._stt_task.done()

    await manager.stop()
    await asyncio.sleep(0.05)

    assert manager._stt_task is None or manager._stt_task.done()
