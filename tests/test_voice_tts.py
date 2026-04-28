"""Unit tests for voice TTS pipeline — sentence splitter and streaming playback."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from daily.voice.tts import TTSPipeline, split_sentences


class TestSplitSentences:
    """Unit tests for the split_sentences utility."""

    def test_normal_multi_sentence_splits_correctly(self) -> None:
        text = "Hello world. How are you today? I'm fine."
        result = split_sentences(text)
        assert len(result) == 3
        assert result[0].strip() == "Hello world."
        assert result[1].strip() == "How are you today?"
        assert result[2].strip() == "I'm fine."

    def test_short_segments_merge(self) -> None:
        # Both "Good." and "Morning." are under MIN_CHARS=30, so they should merge
        text = "Good. Morning."
        result = split_sentences(text)
        assert len(result) == 1
        assert "Good" in result[0]
        assert "Morning" in result[0]

    def test_abbreviation_does_not_split_on_dr(self) -> None:
        text = "Dr. Smith went to Washington. He arrived Tuesday."
        result = split_sentences(text)
        # Should not create a spurious segment from "Dr." alone
        # At minimum, "Dr." should not be its own segment
        assert not any(r.strip() == "Dr." for r in result)
        # Should produce at most 2 segments (not split on "Dr.")
        assert len(result) <= 2

    def test_abbreviation_does_not_split_on_mr(self) -> None:
        text = "Mr. Jones called. He wants a meeting."
        result = split_sentences(text)
        assert not any(r.strip() == "Mr." for r in result)
        assert len(result) <= 2

    def test_empty_string_returns_list_with_original(self) -> None:
        result = split_sentences("")
        assert result == [""]

    def test_single_sentence_no_period_returns_list(self) -> None:
        text = "Single sentence no period"
        result = split_sentences(text)
        assert result == ["Single sentence no period"]

    def test_exclamation_mark_splits(self) -> None:
        text = "Watch out! A car is coming. Stay safe!"
        result = split_sentences(text)
        # Should produce multiple segments (short ones may merge but we expect splits)
        assert len(result) >= 1
        # All original content should be present in the joined result
        joined = " ".join(result)
        assert "Watch out" in joined
        assert "car is coming" in joined

    def test_question_mark_splits(self) -> None:
        text = "What is your name? My name is Alice. Nice to meet you."
        result = split_sentences(text)
        assert len(result) >= 2

    def test_long_segments_do_not_merge(self) -> None:
        # Both sentences are well over MIN_CHARS=30
        s1 = "This is a fairly long first sentence that should not be merged."
        s2 = "This is a fairly long second sentence that should also stand alone."
        result = split_sentences(f"{s1} {s2}")
        assert len(result) == 2

    def test_single_long_sentence(self) -> None:
        text = "This is one complete and fairly long sentence that stands on its own."
        result = split_sentences(text)
        assert result == [text]


def _make_chunk_response(audio_data: bytes) -> MagicMock:
    """Create a mock Cartesia chunk response with audio data."""
    response = MagicMock()
    response.type = "chunk"
    response.audio = audio_data
    return response


def _make_non_chunk_response() -> MagicMock:
    """Create a mock Cartesia non-chunk response (e.g. metadata)."""
    response = MagicMock()
    response.type = "done"
    response.audio = None
    return response


class TestTTSPipeline:
    """Integration-style tests for TTSPipeline with mocked external dependencies."""

    @pytest.mark.asyncio
    async def test_play_streaming_stops_on_event(self) -> None:
        """stop_event set after 2 chunks causes playback to stop before all chunks."""
        # Arrange: 5 chunk responses; we'll set stop_event after 2 are processed
        chunks_written: list[bytes] = []
        stop_event = asyncio.Event()

        audio_data = [b"chunk1", b"chunk2", b"chunk3", b"chunk4", b"chunk5"]
        responses = [_make_chunk_response(d) for d in audio_data]

        async def fake_receive():
            for i, resp in enumerate(responses):
                if i == 2:
                    stop_event.set()
                yield resp

        # Build mock context
        mock_ctx = MagicMock()
        mock_ctx.push = AsyncMock()
        mock_ctx.no_more_inputs = AsyncMock()
        mock_ctx.receive = fake_receive

        # Build mock connection as async context manager
        mock_connection = MagicMock()
        mock_connection.context.return_value = mock_ctx

        # Build mock websocket_connect as async context manager
        mock_ws_cm = MagicMock()
        mock_ws_cm.__aenter__ = AsyncMock(return_value=mock_connection)
        mock_ws_cm.__aexit__ = AsyncMock(return_value=False)

        # Build mock client.tts with websocket_connect method
        mock_tts = MagicMock()
        mock_tts.websocket_connect.return_value = mock_ws_cm

        # Build mock AsyncCartesia as async context manager
        mock_client = MagicMock()
        mock_client.tts = mock_tts
        mock_cartesia_cm = MagicMock()
        mock_cartesia_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cartesia_cm.__aexit__ = AsyncMock(return_value=False)

        # Build mock sounddevice RawOutputStream
        mock_output_stream = MagicMock()
        mock_output_stream.write.side_effect = lambda data: chunks_written.append(data)

        with (
            patch("daily.voice.tts.AsyncCartesia", return_value=mock_cartesia_cm),
            patch("daily.voice.tts.sd.RawOutputStream", return_value=mock_output_stream),
        ):
            pipeline = TTSPipeline(api_key="test-key")
            await pipeline.play_streaming("Hello world.", stop_event)

        # Graceful fade-out: current chunk completes before break (Improvement 3)
        assert len(chunks_written) == 3  # stop_event set at index 2 → chunks 0,1,2 written
        assert stop_event.is_set()

    @pytest.mark.asyncio
    async def test_play_streaming_writes_all_chunks_without_stop(self) -> None:
        """All chunks are written when stop_event is never set."""
        chunks_written: list[bytes] = []
        stop_event = asyncio.Event()

        audio_data = [b"a", b"b", b"c"]
        responses = [_make_chunk_response(d) for d in audio_data]

        async def fake_receive():
            for resp in responses:
                yield resp

        mock_ctx = MagicMock()
        mock_ctx.push = AsyncMock()
        mock_ctx.no_more_inputs = AsyncMock()
        mock_ctx.receive = fake_receive

        mock_connection = MagicMock()
        mock_connection.context.return_value = mock_ctx

        mock_ws_cm = MagicMock()
        mock_ws_cm.__aenter__ = AsyncMock(return_value=mock_connection)
        mock_ws_cm.__aexit__ = AsyncMock(return_value=False)

        mock_tts = MagicMock()
        mock_tts.websocket_connect.return_value = mock_ws_cm

        mock_client = MagicMock()
        mock_client.tts = mock_tts
        mock_cartesia_cm = MagicMock()
        mock_cartesia_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cartesia_cm.__aexit__ = AsyncMock(return_value=False)

        mock_output_stream = MagicMock()
        mock_output_stream.write.side_effect = lambda data: chunks_written.append(data)

        with (
            patch("daily.voice.tts.AsyncCartesia", return_value=mock_cartesia_cm),
            patch("daily.voice.tts.sd.RawOutputStream", return_value=mock_output_stream),
        ):
            pipeline = TTSPipeline(api_key="test-key")
            await pipeline.play_streaming("Hello world.", stop_event)

        assert len(chunks_written) == 3
        assert chunks_written == [b"a", b"b", b"c"]

    @pytest.mark.asyncio
    async def test_play_streaming_closes_stream_on_cancellation(self) -> None:
        """sounddevice stream is closed even when CancelledError is raised (Pitfall 5)."""
        stop_event = asyncio.Event()

        async def fake_receive():
            raise asyncio.CancelledError()
            yield  # make it an async generator

        mock_ctx = MagicMock()
        mock_ctx.push = AsyncMock()
        mock_ctx.no_more_inputs = AsyncMock()
        mock_ctx.receive = fake_receive

        mock_connection = MagicMock()
        mock_connection.context.return_value = mock_ctx

        mock_ws_cm = MagicMock()
        mock_ws_cm.__aenter__ = AsyncMock(return_value=mock_connection)
        mock_ws_cm.__aexit__ = AsyncMock(return_value=False)

        mock_tts = MagicMock()
        mock_tts.websocket_connect.return_value = mock_ws_cm

        mock_client = MagicMock()
        mock_client.tts = mock_tts
        mock_cartesia_cm = MagicMock()
        mock_cartesia_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cartesia_cm.__aexit__ = AsyncMock(return_value=False)

        mock_output_stream = MagicMock()

        with (
            patch("daily.voice.tts.AsyncCartesia", return_value=mock_cartesia_cm),
            patch("daily.voice.tts.sd.RawOutputStream", return_value=mock_output_stream),
        ):
            pipeline = TTSPipeline(api_key="test-key")
            with pytest.raises(asyncio.CancelledError):
                await pipeline.play_streaming("Hello.", stop_event)

        # The stream must be stopped and closed despite the CancelledError
        mock_output_stream.stop.assert_called_once()
        mock_output_stream.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_play_streaming_skips_non_chunk_responses(self) -> None:
        """Non-chunk responses (e.g. done events) are skipped without writing."""
        chunks_written: list[bytes] = []
        stop_event = asyncio.Event()

        responses = [
            _make_non_chunk_response(),
            _make_chunk_response(b"real_audio"),
            _make_non_chunk_response(),
        ]

        async def fake_receive():
            for resp in responses:
                yield resp

        mock_ctx = MagicMock()
        mock_ctx.push = AsyncMock()
        mock_ctx.no_more_inputs = AsyncMock()
        mock_ctx.receive = fake_receive

        mock_connection = MagicMock()
        mock_connection.context.return_value = mock_ctx

        mock_ws_cm = MagicMock()
        mock_ws_cm.__aenter__ = AsyncMock(return_value=mock_connection)
        mock_ws_cm.__aexit__ = AsyncMock(return_value=False)

        mock_tts = MagicMock()
        mock_tts.websocket_connect.return_value = mock_ws_cm

        mock_client = MagicMock()
        mock_client.tts = mock_tts
        mock_cartesia_cm = MagicMock()
        mock_cartesia_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cartesia_cm.__aexit__ = AsyncMock(return_value=False)

        mock_output_stream = MagicMock()
        mock_output_stream.write.side_effect = lambda data: chunks_written.append(data)

        with (
            patch("daily.voice.tts.AsyncCartesia", return_value=mock_cartesia_cm),
            patch("daily.voice.tts.sd.RawOutputStream", return_value=mock_output_stream),
        ):
            pipeline = TTSPipeline(api_key="test-key")
            await pipeline.play_streaming("Hello.", stop_event)

        assert chunks_written == [b"real_audio"]
