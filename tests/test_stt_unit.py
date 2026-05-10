"""Unit tests for STTPipeline event handlers and utility methods in daily.voice.stt.

Tests all synchronous/pure-Python methods without connecting to Deepgram or sounddevice:
  _handle_message, _on_transcript, _on_utterance_end, _on_speech_started_event,
  _display_interim, _finalize_transcript_line, _select_chunk.

deepgram SDK is installed in the venv so we import the real types. Only sounddevice
(which requires hardware / CFFI) is stubbed.
"""
import sys
import types
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Stub only sounddevice — it requires CFFI / PortAudio at import time.
# deepgram is installed in the venv and imported normally.
# ---------------------------------------------------------------------------

_sd_stub = types.ModuleType("sounddevice")
if "sounddevice" not in sys.modules:
    sys.modules["sounddevice"] = _sd_stub

# Now import stt — it will pick up real deepgram types and stubbed sounddevice.
from daily.voice.stt import STTPipeline, _SILENT_CHUNK, _BLOCKSIZE  # noqa: E402

# Import the exact type objects bound in stt.py so isinstance checks match.
from daily.voice.stt import (  # noqa: E402
    ListenV1Results,
    ListenV1UtteranceEnd,
    ListenV1SpeechStarted,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pipeline(**kwargs) -> STTPipeline:
    return STTPipeline(api_key="test-api-key", **kwargs)


def _make_results(text: str = "hello", is_final: bool = True) -> ListenV1Results:
    """Build a minimal ListenV1Results instance using real deepgram type."""
    r = MagicMock(spec=ListenV1Results)
    r.is_final = is_final
    alt = MagicMock()
    alt.transcript = text
    r.channel = MagicMock()
    r.channel.alternatives = [alt]
    return r


# ---------------------------------------------------------------------------
# _handle_message
# ---------------------------------------------------------------------------


class TestHandleMessage:
    """Tests for STTPipeline._handle_message dispatch."""

    def test_dispatches_transcript(self):
        """ListenV1Results messages call _on_transcript."""
        p = _make_pipeline()
        msg = _make_results(text="hello", is_final=True)
        p._handle_message(msg)
        assert p._transcript_parts == ["hello"]

    def test_dispatches_utterance_end(self):
        """ListenV1UtteranceEnd messages call _on_utterance_end."""
        p = _make_pipeline()
        p._transcript_parts = ["hello world"]
        msg = MagicMock(spec=ListenV1UtteranceEnd)
        p._handle_message(msg)
        assert not p.utterance_queue.empty()

    def test_dispatches_speech_started(self):
        """ListenV1SpeechStarted messages invoke _on_speech_started callback."""
        callback = MagicMock()
        p = _make_pipeline(on_speech_started=callback)
        msg = MagicMock(spec=ListenV1SpeechStarted)
        p._handle_message(msg)
        callback.assert_called_once()

    def test_ignores_unknown_message_type(self):
        """Unknown message types are silently ignored."""
        p = _make_pipeline()
        p._handle_message(object())  # should not raise


# ---------------------------------------------------------------------------
# _on_transcript
# ---------------------------------------------------------------------------


class TestOnTranscript:
    def test_final_transcript_accumulated(self):
        """is_final=True transcripts are accumulated in _transcript_parts."""
        p = _make_pipeline()
        p._on_transcript(_make_results(text="hello", is_final=True))
        assert p._transcript_parts == ["hello"]

    def test_interim_transcript_not_accumulated(self):
        """is_final=False transcripts are NOT accumulated."""
        p = _make_pipeline()
        p._on_transcript(_make_results(text="hell", is_final=False))
        assert p._transcript_parts == []

    def test_empty_text_ignored(self):
        """Empty transcript text is ignored entirely."""
        p = _make_pipeline()
        p._on_transcript(_make_results(text="", is_final=True))
        assert p._transcript_parts == []
        assert not p._has_speech_transcript

    def test_sets_has_speech_transcript_flag(self):
        """_has_speech_transcript becomes True when non-empty transcript arrives."""
        p = _make_pipeline()
        assert p._has_speech_transcript is False
        p._on_transcript(_make_results(text="hi", is_final=False))
        assert p._has_speech_transcript is True

    def test_attribute_error_handled_gracefully(self):
        """Malformed result with no channel attribute does not raise."""
        p = _make_pipeline()
        bad = MagicMock()
        bad.channel = None  # accessing .alternatives on None raises AttributeError
        p._on_transcript(bad)

    def test_index_error_handled_gracefully(self):
        """Result with empty alternatives list does not raise."""
        p = _make_pipeline()
        bad = MagicMock()
        bad.channel.alternatives = []
        p._on_transcript(bad)


# ---------------------------------------------------------------------------
# _on_utterance_end
# ---------------------------------------------------------------------------


class TestOnUtteranceEnd:
    def test_pushes_joined_transcript_to_queue(self):
        """Accumulated parts are joined and pushed to utterance_queue."""
        p = _make_pipeline()
        p._transcript_parts = ["hello", "world"]
        p._on_utterance_end(MagicMock(spec=ListenV1UtteranceEnd))
        assert p.utterance_queue.get_nowait() == "hello world"

    def test_clears_transcript_parts_after_flush(self):
        """_transcript_parts is reset to empty after flush."""
        p = _make_pipeline()
        p._transcript_parts = ["hi"]
        p._on_utterance_end(MagicMock(spec=ListenV1UtteranceEnd))
        assert p._transcript_parts == []

    def test_empty_parts_not_pushed(self):
        """Empty accumulated text is not pushed to queue."""
        p = _make_pipeline()
        p._transcript_parts = []
        p._on_utterance_end(MagicMock(spec=ListenV1UtteranceEnd))
        assert p.utterance_queue.empty()

    def test_whitespace_only_not_pushed(self):
        """Whitespace-only accumulated text is not pushed."""
        p = _make_pipeline()
        p._transcript_parts = [" ", "  "]
        p._on_utterance_end(MagicMock(spec=ListenV1UtteranceEnd))
        assert p.utterance_queue.empty()


# ---------------------------------------------------------------------------
# _on_speech_started_event
# ---------------------------------------------------------------------------


class TestOnSpeechStartedEvent:
    def test_callback_invoked_when_not_muted(self):
        """_on_speech_started callback fires when pipeline is not muted."""
        callback = MagicMock()
        p = _make_pipeline(on_speech_started=callback)
        p._on_speech_started_event(MagicMock(spec=ListenV1SpeechStarted))
        callback.assert_called_once()

    def test_callback_suppressed_when_muted(self):
        """Callback is NOT invoked when pipeline is muted (barge-in guard)."""
        callback = MagicMock()
        p = _make_pipeline(on_speech_started=callback)
        p.muted = True
        p._on_speech_started_event(MagicMock(spec=ListenV1SpeechStarted))
        callback.assert_not_called()

    def test_no_callback_registered_is_fine(self):
        """No callback registered — event is silently ignored."""
        p = _make_pipeline()  # no callback
        p._on_speech_started_event(MagicMock(spec=ListenV1SpeechStarted))  # should not raise


# ---------------------------------------------------------------------------
# _select_chunk
# ---------------------------------------------------------------------------


class TestSelectChunk:
    def test_returns_real_audio_when_not_muted(self):
        """Real audio bytes returned when muted=False."""
        p = _make_pipeline()
        real_audio = b"\x01\x02\x03\x04"
        assert p._select_chunk(real_audio) == real_audio

    def test_returns_silent_chunk_when_muted(self):
        """_SILENT_CHUNK returned when muted=True."""
        p = _make_pipeline()
        p.muted = True
        result = p._select_chunk(b"\xff" * 10)
        assert result == _SILENT_CHUNK
        assert len(result) == _BLOCKSIZE * 2


# ---------------------------------------------------------------------------
# Terminal helpers
# ---------------------------------------------------------------------------


class TestTerminalHelpers:
    def test_display_interim_writes_to_stdout(self, capsys):
        """_display_interim writes ANSI in-place update to stdout."""
        STTPipeline._display_interim("hello")
        captured = capsys.readouterr()
        assert "hello" in captured.out

    def test_finalize_transcript_line_writes_you_prefix(self, capsys):
        """_finalize_transcript_line clears line and writes 'You: text'."""
        STTPipeline._finalize_transcript_line("this is my transcript")
        captured = capsys.readouterr()
        assert "You:" in captured.out
        assert "this is my transcript" in captured.out
