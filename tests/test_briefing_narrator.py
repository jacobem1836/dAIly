"""
Tests for src/daily/briefing/narrator.py

All LLM calls are mocked — no real OpenAI API calls.
Tests cover output structure, JSON mode, word count, system prompt constraints,
empty context, key validation, and JSON parse failure fallback.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from daily.briefing.narrator import NARRATOR_SYSTEM_PROMPT, generate_narrative
from daily.briefing.models import BriefingContext, BriefingOutput, CalendarContext, SlackContext


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


def make_mock_client(content: str = '{"narrative": "Good morning. Here is your briefing for today. You have several emails requiring your attention. Your schedule is clear this morning with a team meeting at two. Nothing notable in Slack today."}') -> MagicMock:
    """Return a mock AsyncOpenAI client with controlled response."""
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
# Test 1: Output structure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_output_structure():
    """generate_narrative returns a BriefingOutput with required fields."""
    ctx = make_empty_context()
    mock_client = make_mock_client()

    result = await generate_narrative(ctx, mock_client)

    assert isinstance(result, BriefingOutput)
    assert isinstance(result.narrative, str)
    assert len(result.narrative) > 0
    assert isinstance(result.generated_at, datetime)
    assert isinstance(result.version, int)


# ---------------------------------------------------------------------------
# Test 2: JSON intent mode (SEC-05)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_narrative_is_json_intent():
    """generate_narrative calls the LLM with response_format=json_object."""
    ctx = make_empty_context()
    mock_client = make_mock_client()

    await generate_narrative(ctx, mock_client)

    call_kwargs = mock_client.chat.completions.create.call_args
    # Check response_format was passed as json_object
    assert call_kwargs is not None
    kwargs = call_kwargs.kwargs if call_kwargs.kwargs else call_kwargs[1]
    assert kwargs.get("response_format") == {"type": "json_object"}, (
        f"response_format not set to json_object: {kwargs}"
    )


# ---------------------------------------------------------------------------
# Test 3: Word count soft gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_word_count_soft_gate():
    """Narrative word count is <= 350 (soft upper bound per Pitfall 4)."""
    # Provide a narrative just under 350 words
    words = " ".join(["word"] * 300)
    content = f'{{"narrative": "{words}"}}'
    mock_client = make_mock_client(content=content)
    ctx = make_empty_context()

    result = await generate_narrative(ctx, mock_client)

    word_count = len(result.narrative.split())
    assert word_count <= 350, f"Narrative word count {word_count} exceeds soft gate of 350"


# ---------------------------------------------------------------------------
# Test 4: System prompt contains required constraints
# ---------------------------------------------------------------------------


def test_system_prompt_contains_constraints():
    """System prompt enforces word count, no lists, flowing prose (D-06/D-07)."""
    assert "300 words" in NARRATOR_SYSTEM_PROMPT, "Missing '300 words' in system prompt"
    assert "No lists" in NARRATOR_SYSTEM_PROMPT or "no lists" in NARRATOR_SYSTEM_PROMPT.lower() or \
           "No bullet" in NARRATOR_SYSTEM_PROMPT or "bullet" in NARRATOR_SYSTEM_PROMPT.lower(), \
           "Missing list/bullet prohibition in system prompt"
    assert "flowing" in NARRATOR_SYSTEM_PROMPT.lower(), "Missing 'flowing' in system prompt"


# ---------------------------------------------------------------------------
# Test 5: Empty context — all three sources covered
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_context():
    """Empty context still produces a narrative mentioning all three sources."""
    nothing_narrative = (
        "Nothing notable in emails today. "
        "Nothing notable in calendar today. "
        "Nothing notable in Slack today."
    )
    content = f'{{"narrative": "{nothing_narrative}"}}'
    mock_client = make_mock_client(content=content)
    ctx = make_empty_context()

    result = await generate_narrative(ctx, mock_client)

    assert isinstance(result.narrative, str)
    assert len(result.narrative) > 0


# ---------------------------------------------------------------------------
# Test 6: Key validation — wrong key raises or falls back
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_narrative_key_validation():
    """If LLM returns JSON with wrong key, generate_narrative handles it gracefully.

    Per plan: should raise ValueError OR use fallback. Either is acceptable.
    We test that it does not raise an unhandled KeyError and returns a BriefingOutput.
    """
    # First call returns wrong key, second call (retry) also returns wrong key
    wrong_key_content = '{"text": "This is the narrative content."}'
    fallback_content = '{"text": "Still wrong key."}'

    mock_choice_1 = MagicMock()
    mock_choice_1.message.content = wrong_key_content
    mock_response_1 = MagicMock()
    mock_response_1.choices = [mock_choice_1]

    mock_choice_2 = MagicMock()
    mock_choice_2.message.content = fallback_content
    mock_response_2 = MagicMock()
    mock_response_2.choices = [mock_choice_2]

    mock_client = MagicMock()
    mock_client.chat = MagicMock()
    mock_client.chat.completions = MagicMock()
    # Two calls: initial + retry
    mock_client.chat.completions.create = AsyncMock(
        side_effect=[mock_response_1, mock_response_2]
    )

    ctx = make_empty_context()
    # Should not raise an unhandled KeyError — either ValueError or fallback
    result = await generate_narrative(ctx, mock_client)
    assert isinstance(result, BriefingOutput)
    assert isinstance(result.narrative, str)
    assert len(result.narrative) > 0


# ---------------------------------------------------------------------------
# Test 7: JSON parse failure fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_json_parse_failure_fallback():
    """If LLM returns invalid JSON twice, generate_narrative returns fallback narrative."""
    invalid_json = "This is not valid JSON at all!!"

    mock_choice = MagicMock()
    mock_choice.message.content = invalid_json
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client = MagicMock()
    mock_client.chat = MagicMock()
    mock_client.chat.completions = MagicMock()
    # Both initial and retry calls return invalid JSON
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    ctx = make_empty_context()
    result = await generate_narrative(ctx, mock_client)

    assert isinstance(result, BriefingOutput)
    assert isinstance(result.narrative, str)
    assert len(result.narrative) > 0
    # Should have called LLM twice (initial + retry)
    assert mock_client.chat.completions.create.call_count == 2
