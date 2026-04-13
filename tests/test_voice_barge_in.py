"""Unit tests for VoiceTurnManager barge-in coordination.

Tests cover:
- Normal TTS completion (speak returns True)
- Barge-in cancellation (speak returns False when stop_event set)
- Echo suppression (speech_started during TTS does NOT set stop_event)
- Real barge-in (speech_started when TTS inactive DOES set stop_event)
- stop_event cleared after speak()
- wait_for_utterance returns text from utterance_queue
"""
import asyncio

import pytest

from daily.voice.barge_in import VoiceTurnManager


# ---------------------------------------------------------------------------
# Fakes / mocks
# ---------------------------------------------------------------------------


class _FakeTTS:
    """Fake TTSPipeline that sleeps until stop_event is set or duration elapses."""

    def __init__(self, sleep_duration: float = 10.0) -> None:
        self._sleep_duration = sleep_duration
        self.played: list[str] = []

    async def play_streaming(self, text: str, stop_event: asyncio.Event) -> None:
        self.played.append(text)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=self._sleep_duration)
        except asyncio.TimeoutError:
            pass  # Completed naturally without barge-in


class _FakeTTSInstant:
    """Fake TTSPipeline that returns immediately (no delay)."""

    def __init__(self) -> None:
        self.played: list[str] = []

    async def play_streaming(self, text: str, stop_event: asyncio.Event) -> None:
        self.played.append(text)
        # Return immediately — simulates very short TTS completion


class _FakeSTT:
    """Fake STTPipeline with a public utterance_queue."""

    def __init__(self) -> None:
        self.utterance_queue: asyncio.Queue[str] = asyncio.Queue()
        self._on_speech_started: None = None

    async def start_listening(self, stop_event: asyncio.Event) -> None:
        await stop_event.wait()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_manager(tts=None, stt=None) -> VoiceTurnManager:
    if tts is None:
        tts = _FakeTTSInstant()
    if stt is None:
        stt = _FakeSTT()
    return VoiceTurnManager(tts=tts, stt=stt)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_speak_completes_normally() -> None:
    """speak() returns True when TTS completes without barge-in."""
    manager = _make_manager(tts=_FakeTTSInstant())
    result = await manager.speak("Hello world")
    assert result is True


@pytest.mark.asyncio
async def test_tts_active_false_after_normal_completion() -> None:
    """_tts_active is False after normal speak() completion."""
    manager = _make_manager(tts=_FakeTTSInstant())
    await manager.speak("Hello")
    assert manager._tts_active is False


@pytest.mark.asyncio
async def test_barge_in_cancels_tts() -> None:
    """speak() returns False when stop_event is set externally during playback."""
    fake_tts = _FakeTTS(sleep_duration=10.0)
    manager = _make_manager(tts=fake_tts)

    async def _trigger_barge_in() -> None:
        await asyncio.sleep(0.05)
        manager._stop_event.set()

    asyncio.create_task(_trigger_barge_in())
    result = await manager.speak("Long utterance")
    assert result is False


@pytest.mark.asyncio
async def test_tts_active_false_after_barge_in() -> None:
    """_tts_active is False after speak() interrupted by barge-in."""
    fake_tts = _FakeTTS(sleep_duration=10.0)
    manager = _make_manager(tts=fake_tts)

    async def _trigger() -> None:
        await asyncio.sleep(0.05)
        manager._stop_event.set()

    asyncio.create_task(_trigger())
    await manager.speak("Long")
    assert manager._tts_active is False


@pytest.mark.asyncio
async def test_echo_suppression_during_tts() -> None:
    """_on_speech_started does NOT set stop_event when _tts_active is True."""
    manager = _make_manager()
    manager._tts_active = True
    manager._on_speech_started()
    assert not manager._stop_event.is_set()


@pytest.mark.asyncio
async def test_real_barge_in_when_tts_inactive() -> None:
    """_on_speech_started DOES set stop_event when _tts_active is False."""
    manager = _make_manager()
    manager._tts_active = False
    manager._on_speech_started()
    assert manager._stop_event.is_set()


@pytest.mark.asyncio
async def test_stop_event_cleared_after_speak_normal() -> None:
    """stop_event is cleared after speak() completes normally."""
    manager = _make_manager(tts=_FakeTTSInstant())
    await manager.speak("Hello")
    assert not manager._stop_event.is_set()


@pytest.mark.asyncio
async def test_stop_event_cleared_after_speak_barge_in() -> None:
    """stop_event is cleared after speak() is interrupted by barge-in."""
    fake_tts = _FakeTTS(sleep_duration=10.0)
    manager = _make_manager(tts=fake_tts)

    async def _trigger() -> None:
        await asyncio.sleep(0.05)
        manager._stop_event.set()

    asyncio.create_task(_trigger())
    await manager.speak("Long")
    assert not manager._stop_event.is_set()


@pytest.mark.asyncio
async def test_wait_for_utterance_returns_text() -> None:
    """wait_for_utterance() returns the next text from STT utterance_queue."""
    fake_stt = _FakeSTT()
    manager = _make_manager(stt=fake_stt)

    fake_stt.utterance_queue.put_nowait("What is the weather?")
    result = await manager.wait_for_utterance()
    assert result == "What is the weather?"


@pytest.mark.asyncio
async def test_start_stt_wires_speech_started_callback() -> None:
    """start_stt() wires a callback into the STT pipeline that triggers barge-in."""
    fake_stt = _FakeSTT()
    manager = _make_manager(stt=fake_stt)

    listen_stop = asyncio.Event()
    listen_stop.set()  # Stop immediately so start_listening exits
    await manager.start_stt(listen_stop)

    # The STT pipeline should have a callable callback assigned
    assert fake_stt._on_speech_started is not None
    assert callable(fake_stt._on_speech_started)

    # Calling the wired callback when tts_active=False should set stop_event
    manager._tts_active = False
    fake_stt._on_speech_started()
    assert manager._stop_event.is_set()


@pytest.mark.asyncio
async def test_stop_cancels_tts_task() -> None:
    """stop() cancels an in-flight TTS task."""
    fake_tts = _FakeTTS(sleep_duration=30.0)
    manager = _make_manager(tts=fake_tts)

    # Start speak in background, then stop immediately
    speak_task = asyncio.create_task(manager.speak("Long utterance"))
    await asyncio.sleep(0.05)
    await manager.stop()

    # speak_task should resolve (False) since TTS was cancelled
    result = await asyncio.wait_for(speak_task, timeout=1.0)
    assert result is False
