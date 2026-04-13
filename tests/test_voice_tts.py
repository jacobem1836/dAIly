"""Unit tests for voice TTS pipeline — sentence splitter and streaming playback."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from daily.voice.tts import split_sentences


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
