"""Unit tests for orchestrator/session.py astream_session and _looks_like_respond_intent.

Covers:
- StreamingNotSupported raised for non-respond keywords
- astream_session yields token deltas from mocked OpenAI stream
- astream_session with initial_state preferences
- _looks_like_respond_intent with respond and non-respond inputs
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# _looks_like_respond_intent
# ---------------------------------------------------------------------------


def test_looks_like_respond_intent_plain_question():
    """A plain question has no non-respond keyword — returns True."""
    from daily.orchestrator.session import _looks_like_respond_intent

    assert _looks_like_respond_intent("Tell me about my morning") is True


def test_looks_like_respond_intent_empty_string():
    """Empty string has no keywords — returns True (edge case)."""
    from daily.orchestrator.session import _looks_like_respond_intent

    assert _looks_like_respond_intent("") is True


def test_looks_like_respond_intent_draft_keyword():
    """'draft' keyword causes False."""
    from daily.orchestrator.session import _looks_like_respond_intent

    assert _looks_like_respond_intent("Can you draft a reply to Alice?") is False


def test_looks_like_respond_intent_summarise_keyword():
    """'summarise' keyword causes False."""
    from daily.orchestrator.session import _looks_like_respond_intent

    assert _looks_like_respond_intent("Can you summarise that email?") is False


def test_looks_like_respond_intent_exit_keyword():
    """'exit' keyword causes False."""
    from daily.orchestrator.session import _looks_like_respond_intent

    assert _looks_like_respond_intent("exit") is False


def test_looks_like_respond_intent_case_insensitive():
    """Matching is case-insensitive."""
    from daily.orchestrator.session import _looks_like_respond_intent

    assert _looks_like_respond_intent("DRAFT an email") is False
    # "schedule" is a non-respond keyword — normalised SCHEDULE matches it
    assert _looks_like_respond_intent("SCHEDULE a meeting") is False
    # A plain question with no keywords returns True
    assert _looks_like_respond_intent("What is on my AGENDA today?") is True


# ---------------------------------------------------------------------------
# astream_session — StreamingNotSupported path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_astream_session_raises_for_non_respond_intent():
    """astream_session raises StreamingNotSupported for non-respond keywords."""
    from daily.orchestrator.session import astream_session, StreamingNotSupported

    with pytest.raises(StreamingNotSupported):
        async for _ in astream_session(
            graph=MagicMock(),
            user_input="draft a reply to Alice",
            config={},
        ):
            pass


@pytest.mark.asyncio
async def test_astream_session_raises_error_message_contains_input():
    """StreamingNotSupported message includes the rejected user input."""
    from daily.orchestrator.session import astream_session, StreamingNotSupported

    with pytest.raises(StreamingNotSupported, match="non-respond intent"):
        async for _ in astream_session(
            graph=MagicMock(),
            user_input="summarise my emails",
            config={},
        ):
            pass


# ---------------------------------------------------------------------------
# astream_session — success path (mocked OpenAI)
# ---------------------------------------------------------------------------


def _make_chunk(content: str | None):
    """Build a minimal mock OpenAI streaming chunk."""
    chunk = MagicMock()
    chunk.choices[0].delta.content = content
    return chunk


async def _fake_stream(*contents):
    """Async generator that yields mock chunks."""
    for c in contents:
        yield _make_chunk(c)


@pytest.mark.asyncio
async def test_astream_session_yields_token_deltas():
    """astream_session yields non-None delta content from OpenAI stream."""
    from daily.orchestrator.session import astream_session

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_fake_stream("Hello", " there", None, "!")
    )

    with (
        patch("daily.config.Settings") as mock_settings_cls,
        patch("openai.AsyncOpenAI", return_value=mock_client),
    ):
        mock_settings_cls.return_value.openai_api_key = "fake-key"

        tokens = []
        async for tok in astream_session(
            graph=MagicMock(),
            user_input="What is on my calendar today?",
            config={},
        ):
            tokens.append(tok)

    # None delta should be filtered out
    assert tokens == ["Hello", " there", "!"]


@pytest.mark.asyncio
async def test_astream_session_with_initial_state():
    """astream_session uses initial_state preferences when provided."""
    from daily.orchestrator.session import astream_session

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_fake_stream("Good morning")
    )

    initial_state = {
        "briefing_narrative": "You have 2 meetings today.",
        "preferences": {"tone": "formal", "briefing_length": "brief"},
    }

    with (
        patch("daily.config.Settings") as mock_settings_cls,
        patch("openai.AsyncOpenAI", return_value=mock_client),
    ):
        mock_settings_cls.return_value.openai_api_key = "fake-key"

        tokens = []
        async for tok in astream_session(
            graph=MagicMock(),
            user_input="What are my meetings?",
            config={},
            initial_state=initial_state,
        ):
            tokens.append(tok)

    assert tokens == ["Good morning"]
    # Verify the client was called (once for the streaming request)
    mock_client.chat.completions.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_astream_session_skips_none_deltas():
    """None delta values in the stream are not yielded."""
    from daily.orchestrator.session import astream_session

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_fake_stream(None, None, "hi", None)
    )

    with (
        patch("daily.config.Settings") as mock_settings_cls,
        patch("openai.AsyncOpenAI", return_value=mock_client),
    ):
        mock_settings_cls.return_value.openai_api_key = "fake-key"

        tokens = []
        async for tok in astream_session(
            graph=MagicMock(),
            user_input="Hello there",
            config={},
        ):
            tokens.append(tok)

    assert tokens == ["hi"]
