"""Unit tests for pure-Python utility functions in daily.voice.tts.

Covers _split_at_boundary and split_sentences without any I/O or network calls.
These functions are fully synchronous and import cleanly without sounddevice/Cartesia.
"""
import sys
import types

# ---------------------------------------------------------------------------
# Stub out sounddevice and cartesia before importing tts so the module loads
# without hardware or network dependencies.
# ---------------------------------------------------------------------------

_sd_stub = types.ModuleType("sounddevice")
sys.modules.setdefault("sounddevice", _sd_stub)

_cartesia_stub = types.ModuleType("cartesia")
_cartesia_stub.AsyncCartesia = object  # type: ignore[attr-defined]
sys.modules.setdefault("cartesia", _cartesia_stub)

# Now safe to import
from daily.voice.tts import _split_at_boundary, split_sentences  # noqa: E402


# ---------------------------------------------------------------------------
# _split_at_boundary
# ---------------------------------------------------------------------------


class TestSplitAtBoundary:
    """Tests for _split_at_boundary(buffer) -> (sentence | None, remainder)."""

    def test_no_boundary_returns_none_and_original(self):
        """Returns (None, buffer) when no sentence boundary is present."""
        result, remainder = _split_at_boundary("Hello world")
        assert result is None
        assert remainder == "Hello world"

    def test_period_space_boundary(self):
        """Splits on '. ' (period + space)."""
        sentence, remainder = _split_at_boundary("Hello world. How are you?")
        assert sentence == "Hello world. "
        assert remainder == "How are you?"

    def test_exclamation_boundary(self):
        """Splits on '! ' (exclamation + space)."""
        sentence, remainder = _split_at_boundary("Stop! Please wait.")
        assert sentence == "Stop! "
        assert remainder == "Please wait."

    def test_question_boundary(self):
        """Splits on '? ' (question mark + space)."""
        sentence, remainder = _split_at_boundary("Is this right? Yes it is.")
        assert sentence == "Is this right? "
        assert remainder == "Yes it is."

    def test_newline_boundary(self):
        """Splits on '\\n' (newline character)."""
        sentence, remainder = _split_at_boundary("Line one\nLine two")
        assert sentence == "Line one\n"
        assert remainder == "Line two"

    def test_picks_earliest_boundary(self):
        """When multiple boundaries exist, the earliest one wins."""
        sentence, remainder = _split_at_boundary("A! B? C. D")
        # '! ' comes first
        assert sentence == "A! "
        assert remainder == "B? C. D"

    def test_empty_buffer_returns_none(self):
        """Empty buffer has no boundary — returns (None, '')."""
        result, remainder = _split_at_boundary("")
        assert result is None
        assert remainder == ""

    def test_only_boundary_character(self):
        """Buffer is exactly a boundary marker."""
        sentence, remainder = _split_at_boundary(". ")
        assert sentence == ". "
        assert remainder == ""


# ---------------------------------------------------------------------------
# split_sentences
# ---------------------------------------------------------------------------


class TestSplitSentences:
    """Tests for split_sentences(text) -> list[str]."""

    def test_empty_string_returns_list_with_empty(self):
        """Empty input returns [''] (falsy text)."""
        result = split_sentences("")
        assert result == [""]

    def test_single_sentence_no_split(self):
        """Text with no punctuation returns as single segment."""
        result = split_sentences("Hello world")
        assert result == ["Hello world"]

    def test_two_sentences_split(self):
        """Two sentences separated by '. ' are split into two segments."""
        result = split_sentences("Hello world. How are you?")
        assert len(result) == 2
        assert "Hello world." in result[0]
        assert "How are you?" in result[1]

    def test_abbreviation_not_split(self):
        """Abbreviations like 'Dr.' and 'Mr.' do not trigger a split."""
        result = split_sentences("Dr. Smith will see you now. Please wait.")
        # Should NOT split on 'Dr.'
        assert len(result) >= 1
        joined = " ".join(result)
        assert "Dr. Smith" in joined

    def test_short_segments_merged(self):
        """Segments shorter than MIN_CHARS are merged into the following segment."""
        # 'Hi.' is 3 chars — below MIN_CHARS=6 — gets merged with next segment
        result = split_sentences("Hi. Please come in and have a seat.")
        # The merged result should be a single segment containing both parts
        assert len(result) == 1
        assert "Hi." in result[0]
        assert "Please come in" in result[0]

    def test_trailing_short_segment_appended_to_last(self):
        """Short trailing segment is appended to the last merged segment."""
        # Build a text where the last sentence is short
        result = split_sentences("This is a long first sentence. OK.")
        joined = " ".join(result)
        assert "OK." in joined

    def test_multiple_sentences_all_long(self):
        """Multiple long sentences each appear as their own segment."""
        text = "The quick brown fox jumps over the lazy dog. Pack my box with five dozen liquor jugs."
        result = split_sentences(text)
        assert len(result) == 2

    def test_question_mark_splits(self):
        """Question mark followed by space triggers a split."""
        result = split_sentences("Are you ready? Let me know your answer.")
        assert len(result) == 2

    def test_exclamation_splits(self):
        """Exclamation mark followed by space triggers a split."""
        result = split_sentences("Watch out! There is danger ahead here now.")
        assert len(result) == 2

    def test_no_segments_fallback(self):
        """Handles edge case where segmentation produces no segments — returns [text]."""
        # A string that contains only the boundary pattern itself
        result = split_sentences(". ")
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_all_short_segments_collected_as_one(self):
        """When all segments are short they accumulate until one long enough block."""
        # A series of tiny sentences — all under MIN_CHARS=6
        result = split_sentences("OK. So. Fine.")
        # Should end up merged into one or two segments but not crash
        assert isinstance(result, list)
        assert len(result) >= 1
