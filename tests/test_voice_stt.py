"""Unit tests for STTPipeline — Deepgram Nova-3 WebSocket STT pipeline.

Tests use mocked Deepgram SDK and sounddevice to avoid hardware/network dependencies.

Covers:
- Interim transcript handling (not accumulated, not queued)
- Final transcript accumulation
- UtteranceEnd joining and queue push
- UtteranceEnd with empty buffer (no queue push)
- speech_started callback invocation
"""

import asyncio
from unittest.mock import MagicMock

import pytest

from daily.voice.stt import STTPipeline


@pytest.fixture
def stt() -> STTPipeline:
    """Return a bare STTPipeline with a dummy API key and no callback."""
    return STTPipeline(api_key="test-key")


@pytest.fixture
def stt_with_callback() -> tuple[STTPipeline, MagicMock]:
    """Return (STTPipeline, mock_callback) for testing speech_started wiring."""
    cb = MagicMock()
    pipeline = STTPipeline(api_key="test-key", on_speech_started=cb)
    return pipeline, cb


# ---------------------------------------------------------------------------
# Helpers: build fake Deepgram message objects matching SDK types
# ---------------------------------------------------------------------------

def _make_transcript_result(text: str, is_final: bool) -> object:
    """Build a fake message that passes isinstance(msg, ListenV1Results).

    Uses __class__ override on a MagicMock so that isinstance() returns True
    without requiring a valid Pydantic object construction.
    """
    from deepgram.listen.v1.types import ListenV1Results

    alt = MagicMock()
    alt.transcript = text
    channel = MagicMock()
    channel.alternatives = [alt]

    msg = MagicMock()
    msg.is_final = is_final
    msg.channel = channel
    # Override __class__ so isinstance(msg, ListenV1Results) is True
    msg.__class__ = ListenV1Results
    return msg


def _make_interim_result(text: str) -> object:
    """Simulate a ListenV1Results message with is_final=False."""
    return _make_transcript_result(text, is_final=False)


def _make_final_result(text: str) -> object:
    """Simulate a ListenV1Results message with is_final=True."""
    return _make_transcript_result(text, is_final=True)


def _make_utterance_end() -> object:
    """Simulate a ListenV1UtteranceEnd message."""
    from deepgram.listen.v1.types import ListenV1UtteranceEnd

    msg = MagicMock()
    msg.__class__ = ListenV1UtteranceEnd
    return msg


def _make_speech_started() -> object:
    """Simulate a ListenV1SpeechStarted message."""
    from deepgram.listen.v1.types import ListenV1SpeechStarted

    msg = MagicMock()
    msg.__class__ = ListenV1SpeechStarted
    return msg


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestInterimTranscripts:
    def test_interim_transcript_not_accumulated(self, stt: STTPipeline) -> None:
        """Interim transcripts must NOT be added to _transcript_parts."""
        msg = _make_interim_result("hello")
        stt._handle_message(msg)
        assert stt._transcript_parts == []

    def test_interim_transcript_not_queued(self, stt: STTPipeline) -> None:
        """Interim transcripts must NOT push anything to utterance_queue."""
        msg = _make_interim_result("hello")
        stt._handle_message(msg)
        assert stt.utterance_queue.empty()


class TestFinalTranscripts:
    def test_final_transcript_accumulated(self, stt: STTPipeline) -> None:
        """A final transcript must be appended to _transcript_parts."""
        msg = _make_final_result("hello world")
        stt._handle_message(msg)
        assert stt._transcript_parts == ["hello world"]

    def test_multiple_finals_accumulated(self, stt: STTPipeline) -> None:
        """Multiple final transcripts accumulate in order."""
        stt._handle_message(_make_final_result("first"))
        stt._handle_message(_make_final_result("second"))
        assert stt._transcript_parts == ["first", "second"]

    def test_empty_final_not_accumulated(self, stt: STTPipeline) -> None:
        """A final transcript with empty text should not be appended."""
        stt._handle_message(_make_final_result(""))
        assert stt._transcript_parts == []


class TestUtteranceEnd:
    def test_utterance_end_sends_to_queue(self, stt: STTPipeline) -> None:
        """After 2 finals, UtteranceEnd should push joined text to queue."""
        stt._handle_message(_make_final_result("hello"))
        stt._handle_message(_make_final_result("world"))
        stt._handle_message(_make_utterance_end())
        result = stt.utterance_queue.get_nowait()
        assert result == "hello world"

    def test_utterance_end_clears_buffer(self, stt: STTPipeline) -> None:
        """After UtteranceEnd, _transcript_parts must be cleared."""
        stt._handle_message(_make_final_result("something"))
        stt._handle_message(_make_utterance_end())
        assert stt._transcript_parts == []

    def test_utterance_end_empty_no_queue(self, stt: STTPipeline) -> None:
        """UtteranceEnd with no accumulated text must NOT push to queue."""
        stt._handle_message(_make_utterance_end())
        assert stt.utterance_queue.empty()

    def test_utterance_end_single_word(self, stt: STTPipeline) -> None:
        """Single final before UtteranceEnd pushes exactly that word."""
        stt._handle_message(_make_final_result("yes"))
        stt._handle_message(_make_utterance_end())
        result = stt.utterance_queue.get_nowait()
        assert result == "yes"


class TestSpeechStartedCallback:
    def test_speech_started_callback_called(self, stt_with_callback: tuple[STTPipeline, MagicMock]) -> None:
        """speech_started event must invoke the on_speech_started callback."""
        pipeline, cb = stt_with_callback
        pipeline._handle_message(_make_speech_started())
        cb.assert_called_once()

    def test_no_callback_does_not_raise(self, stt: STTPipeline) -> None:
        """speech_started with no callback set must not raise."""
        stt._handle_message(_make_speech_started())  # Should not raise

    def test_speech_started_does_not_queue(self, stt: STTPipeline) -> None:
        """speech_started event must not push anything to utterance_queue."""
        stt._handle_message(_make_speech_started())
        assert stt.utterance_queue.empty()


class TestSTTPipelineInterface:
    def test_has_utterance_queue(self, stt: STTPipeline) -> None:
        """STTPipeline must expose utterance_queue."""
        assert isinstance(stt.utterance_queue, asyncio.Queue)

    def test_has_start_listening(self, stt: STTPipeline) -> None:
        """STTPipeline must expose start_listening coroutine."""
        assert asyncio.iscoroutinefunction(stt.start_listening)
