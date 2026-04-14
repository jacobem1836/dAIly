"""
Tests for preference-aware narrator system prompt (Task 2 TDD).

Tests cover:
- build_narrator_system_prompt(UserPreferences()) returns prompt containing "tone=conversational" and "length=standard"
- build_narrator_system_prompt(UserPreferences(tone="formal", briefing_length="concise")) returns prompt with "tone=formal" and "length=concise"
- build_narrator_system_prompt includes category_order in structure instruction
- generate_narrative with preferences=None uses default NARRATOR_SYSTEM_PROMPT (backward compatible)
- generate_narrative with preferences=UserPreferences(tone="casual") prepends preamble to system prompt
- max_tokens adjusts based on briefing_length
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from daily.briefing.models import BriefingContext, BriefingOutput, CalendarContext, SlackContext
from daily.profile.models import UserPreferences


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_empty_context() -> BriefingContext:
    return BriefingContext(
        user_id=1,
        generated_at=datetime(2026, 4, 7, 6, 0, 0),
        emails=[],
        calendar=CalendarContext(events=[], conflicts=[]),
        slack=SlackContext(messages=[]),
    )


def make_mock_client(content: str = '{"narrative": "Good morning briefing."}') -> MagicMock:
    mock_choice = MagicMock()
    mock_choice.message.content = content
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_client = MagicMock()
    mock_client.chat = MagicMock()
    mock_client.chat.completions = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
    return mock_client


# ---------------------------------------------------------------------------
# Test build_narrator_system_prompt function
# ---------------------------------------------------------------------------


class TestBuildNarratorSystemPrompt:
    def test_no_preferences_returns_base_prompt(self):
        """build_narrator_system_prompt(None) returns NARRATOR_SYSTEM_PROMPT unchanged."""
        from daily.briefing.narrator import NARRATOR_SYSTEM_PROMPT, build_narrator_system_prompt

        result = build_narrator_system_prompt(None)
        assert result == NARRATOR_SYSTEM_PROMPT

    def test_default_preferences_includes_tone_conversational(self):
        """build_narrator_system_prompt(UserPreferences()) includes tone=conversational."""
        from daily.briefing.narrator import build_narrator_system_prompt

        result = build_narrator_system_prompt(UserPreferences())
        assert "conversational" in result, f"Expected 'conversational' in prompt: {result[:200]}"

    def test_default_preferences_includes_length_standard(self):
        """build_narrator_system_prompt(UserPreferences()) includes length=standard."""
        from daily.briefing.narrator import build_narrator_system_prompt

        result = build_narrator_system_prompt(UserPreferences())
        assert "standard" in result, f"Expected 'standard' in prompt: {result[:200]}"

    def test_formal_concise_preferences(self):
        """build_narrator_system_prompt with formal/concise preferences includes those values."""
        from daily.briefing.narrator import build_narrator_system_prompt

        prefs = UserPreferences(tone="formal", briefing_length="concise")
        result = build_narrator_system_prompt(prefs)
        assert "formal" in result, f"Expected 'formal' in prompt: {result[:200]}"
        assert "concise" in result, f"Expected 'concise' in prompt: {result[:200]}"

    def test_preferences_includes_category_order(self):
        """build_narrator_system_prompt includes category_order in the prompt."""
        from daily.briefing.narrator import build_narrator_system_prompt

        prefs = UserPreferences(category_order=["calendar", "emails", "slack"])
        result = build_narrator_system_prompt(prefs)
        assert "calendar" in result, f"Expected 'calendar' in prompt: {result[:300]}"
        assert "emails" in result, f"Expected 'emails' in prompt: {result[:300]}"

    def test_preferences_prompt_prepended_to_base_prompt(self):
        """build_narrator_system_prompt(prefs) starts with preference preamble, ends with base."""
        from daily.briefing.narrator import NARRATOR_SYSTEM_PROMPT, build_narrator_system_prompt

        prefs = UserPreferences(tone="casual")
        result = build_narrator_system_prompt(prefs)
        # Preamble comes first
        assert result.startswith("User preferences:")
        # Base prompt is appended after the preamble
        assert NARRATOR_SYSTEM_PROMPT in result

    def test_preamble_contains_preference_preamble_constant(self):
        """PREFERENCE_PREAMBLE constant is defined in narrator module."""
        from daily.briefing import narrator
        assert hasattr(narrator, "PREFERENCE_PREAMBLE"), "PREFERENCE_PREAMBLE not defined in narrator"

    def test_concise_word_count_instruction_in_preamble(self):
        """PREFERENCE_PREAMBLE includes word count guidance for 'concise' length."""
        from daily.briefing.narrator import PREFERENCE_PREAMBLE
        assert "100" in PREFERENCE_PREAMBLE or "concise" in PREFERENCE_PREAMBLE.lower()

    def test_detailed_word_count_instruction_in_preamble(self):
        """PREFERENCE_PREAMBLE includes word count guidance for 'detailed' length."""
        from daily.briefing.narrator import PREFERENCE_PREAMBLE
        assert "350" in PREFERENCE_PREAMBLE or "detailed" in PREFERENCE_PREAMBLE.lower()


# ---------------------------------------------------------------------------
# Test generate_narrative backward compatibility
# ---------------------------------------------------------------------------


class TestGenerateNarrativeBackwardCompat:
    @pytest.mark.asyncio
    async def test_no_preferences_uses_base_system_prompt(self):
        """generate_narrative with preferences=None uses NARRATOR_SYSTEM_PROMPT."""
        from daily.briefing.narrator import NARRATOR_SYSTEM_PROMPT, generate_narrative

        ctx = make_empty_context()
        mock_client = make_mock_client()

        await generate_narrative(ctx, mock_client)

        call_kwargs = mock_client.chat.completions.create.call_args
        kwargs = call_kwargs.kwargs if call_kwargs.kwargs else call_kwargs[1]
        messages = kwargs.get("messages", call_kwargs[0][1] if call_kwargs[0] else [])
        system_message = next((m for m in messages if m["role"] == "system"), None)
        assert system_message is not None
        assert system_message["content"] == NARRATOR_SYSTEM_PROMPT

    @pytest.mark.asyncio
    async def test_no_preferences_returns_briefing_output(self):
        """generate_narrative(ctx, client) without preferences returns BriefingOutput."""
        from daily.briefing.narrator import generate_narrative

        ctx = make_empty_context()
        mock_client = make_mock_client()

        result = await generate_narrative(ctx, mock_client)
        assert isinstance(result, BriefingOutput)

    @pytest.mark.asyncio
    async def test_explicit_none_preferences_behaves_as_no_preferences(self):
        """generate_narrative(ctx, client, preferences=None) is same as omitting it."""
        from daily.briefing.narrator import NARRATOR_SYSTEM_PROMPT, generate_narrative

        ctx = make_empty_context()
        mock_client = make_mock_client()

        result = await generate_narrative(ctx, mock_client, preferences=None)
        assert isinstance(result, BriefingOutput)

        call_kwargs = mock_client.chat.completions.create.call_args
        kwargs = call_kwargs.kwargs if call_kwargs.kwargs else call_kwargs[1]
        messages = kwargs.get("messages", [])
        system_message = next((m for m in messages if m["role"] == "system"), None)
        assert system_message["content"] == NARRATOR_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Test generate_narrative with preferences
# ---------------------------------------------------------------------------


class TestGenerateNarrativeWithPreferences:
    @pytest.mark.asyncio
    async def test_casual_tone_preference_in_system_prompt(self):
        """generate_narrative with tone=casual includes 'casual' in system message content."""
        from daily.briefing.narrator import generate_narrative

        ctx = make_empty_context()
        mock_client = make_mock_client()
        prefs = UserPreferences(tone="casual")

        await generate_narrative(ctx, mock_client, preferences=prefs)

        call_kwargs = mock_client.chat.completions.create.call_args
        kwargs = call_kwargs.kwargs if call_kwargs.kwargs else call_kwargs[1]
        messages = kwargs.get("messages", [])
        system_message = next((m for m in messages if m["role"] == "system"), None)
        assert system_message is not None
        assert "casual" in system_message["content"]

    @pytest.mark.asyncio
    async def test_formal_tone_preference_in_system_prompt(self):
        """generate_narrative with tone=formal includes 'formal' in system message."""
        from daily.briefing.narrator import generate_narrative

        ctx = make_empty_context()
        mock_client = make_mock_client()
        prefs = UserPreferences(tone="formal", briefing_length="detailed")

        await generate_narrative(ctx, mock_client, preferences=prefs)

        call_kwargs = mock_client.chat.completions.create.call_args
        kwargs = call_kwargs.kwargs if call_kwargs.kwargs else call_kwargs[1]
        messages = kwargs.get("messages", [])
        system_message = next((m for m in messages if m["role"] == "system"), None)
        assert "formal" in system_message["content"]
        assert "detailed" in system_message["content"]

    @pytest.mark.asyncio
    async def test_concise_max_tokens_reduced(self):
        """generate_narrative with concise length uses lower max_tokens (<=450)."""
        from daily.briefing.narrator import generate_narrative

        ctx = make_empty_context()
        mock_client = make_mock_client()
        prefs = UserPreferences(briefing_length="concise")

        await generate_narrative(ctx, mock_client, preferences=prefs)

        call_kwargs = mock_client.chat.completions.create.call_args
        kwargs = call_kwargs.kwargs if call_kwargs.kwargs else call_kwargs[1]
        max_tokens = kwargs.get("max_tokens")
        assert max_tokens is not None
        assert max_tokens <= 450, f"Expected concise max_tokens <= 450, got {max_tokens}"

    @pytest.mark.asyncio
    async def test_detailed_max_tokens_increased(self):
        """generate_narrative with detailed length uses higher max_tokens (>=700)."""
        from daily.briefing.narrator import generate_narrative

        ctx = make_empty_context()
        mock_client = make_mock_client()
        prefs = UserPreferences(briefing_length="detailed")

        await generate_narrative(ctx, mock_client, preferences=prefs)

        call_kwargs = mock_client.chat.completions.create.call_args
        kwargs = call_kwargs.kwargs if call_kwargs.kwargs else call_kwargs[1]
        max_tokens = kwargs.get("max_tokens")
        assert max_tokens is not None
        assert max_tokens >= 700, f"Expected detailed max_tokens >= 700, got {max_tokens}"
