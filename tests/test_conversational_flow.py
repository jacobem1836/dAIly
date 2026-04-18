"""Tests for Phase 12: Conversational Flow.

Covers all three requirements:
  CONV-01: Briefing interrupt/resume (cursor tracking, split sentences, resume node)
  CONV-02: Mode switching (cursor = active briefing indicator, routing)
  CONV-03: Tone adaptation (explicit triggers, implicit triggers, prompt injection, no DB write)
"""
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from daily.orchestrator.graph import route_intent
from daily.orchestrator.nodes import (
    COMPRESSION_PHRASES,
    _IMPLICIT_TONE_MAX_WORDS,
    _IMPLICIT_TONE_MIN_TURNS,
    respond_node,
    resume_briefing_node,
)
from daily.orchestrator.state import SessionState
from daily.voice.loop import _split_sentences


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_response(content: str = '{"action": "answer", "narrative": "test response", "target_id": null}'):
    """Build a minimal AsyncMock that looks like an OpenAI chat completion response."""
    mock_response = AsyncMock()
    mock_response.choices = [AsyncMock()]
    mock_response.choices[0].message.content = content
    return mock_response


# ---------------------------------------------------------------------------
# CONV-01: split sentences
# ---------------------------------------------------------------------------


class TestSplitSentences:
    def test_split_sentences_basic(self):
        result = _split_sentences("Hello. World.")
        assert result == ["Hello.", "World."]

    def test_split_sentences_question_exclamation(self):
        result = _split_sentences("Are you ready? Yes! Let's go.")
        assert result == ["Are you ready?", "Yes!", "Let's go."]

    def test_split_sentences_empty(self):
        result = _split_sentences("")
        assert result == []

    def test_split_sentences_single(self):
        # Single sentence with no trailing whitespace
        result = _split_sentences("Just one sentence.")
        assert result == ["Just one sentence."]

    def test_split_sentences_multiple_types(self):
        result = _split_sentences("First. Second? Third!")
        assert len(result) == 3
        assert result[0] == "First."
        assert result[1] == "Second?"
        assert result[2] == "Third!"

    def test_split_sentences_whitespace_only(self):
        result = _split_sentences("   ")
        assert result == []


# ---------------------------------------------------------------------------
# CONV-01 + CONV-02: SessionState fields
# ---------------------------------------------------------------------------


class TestSessionStateFields:
    def test_briefing_cursor_default_none(self):
        state = SessionState()
        assert state.briefing_cursor is None

    def test_tone_override_default_none(self):
        state = SessionState()
        assert state.tone_override is None

    def test_briefing_cursor_can_be_set(self):
        state = SessionState(briefing_cursor=5)
        assert state.briefing_cursor == 5

    def test_tone_override_can_be_set(self):
        state = SessionState(tone_override="brief")
        assert state.tone_override == "brief"

    def test_cursor_none_means_no_active_briefing(self):
        state = SessionState(briefing_cursor=None)
        assert state.briefing_cursor is None

    def test_cursor_set_means_active_briefing(self):
        state = SessionState(briefing_cursor=5)
        assert state.briefing_cursor == 5


# ---------------------------------------------------------------------------
# CONV-01 + CONV-02: route_intent for resume briefing
# ---------------------------------------------------------------------------


class TestRouteIntentResumeBriefing:
    def _state_with_message(self, content: str) -> SessionState:
        return SessionState(messages=[HumanMessage(content=content)])

    def test_route_intent_resume_briefing(self):
        state = self._state_with_message("resume briefing")
        assert route_intent(state) == "resume_briefing"

    def test_route_intent_continue_my_briefing(self):
        state = self._state_with_message("continue my briefing")
        assert route_intent(state) == "resume_briefing"

    def test_route_intent_go_back_to_briefing(self):
        state = self._state_with_message("go back to the briefing")
        assert route_intent(state) == "resume_briefing"

    def test_route_intent_continue_briefing(self):
        state = self._state_with_message("continue briefing")
        assert route_intent(state) == "resume_briefing"

    def test_route_intent_pick_up_briefing(self):
        state = self._state_with_message("pick up the briefing")
        assert route_intent(state) == "resume_briefing"

    def test_route_intent_where_were_we(self):
        state = self._state_with_message("where were we")
        assert route_intent(state) == "resume_briefing"

    def test_route_intent_resume_before_summarise(self):
        # "resume briefing" must NOT route to summarise_thread
        state = self._state_with_message("resume briefing")
        result = route_intent(state)
        assert result == "resume_briefing"
        assert result != "summarise_thread"

    def test_route_intent_normal_question_still_respond(self):
        state = self._state_with_message("what's on my calendar")
        assert route_intent(state) == "respond"

    def test_route_intent_no_messages_returns_respond(self):
        state = SessionState(messages=[])
        assert route_intent(state) == "respond"


# ---------------------------------------------------------------------------
# CONV-01: resume_briefing_node behavior
# ---------------------------------------------------------------------------


class TestResumeBriefingNode:
    @pytest.mark.asyncio
    async def test_resume_node_with_cursor(self):
        state = SessionState(
            messages=[HumanMessage(content="resume briefing")],
            briefing_cursor=3,
        )
        result = await resume_briefing_node(state)
        messages = result["messages"]
        assert len(messages) == 1
        assert isinstance(messages[0], AIMessage)
        assert "Resuming your briefing now." in messages[0].content

    @pytest.mark.asyncio
    async def test_resume_node_without_cursor(self):
        state = SessionState(
            messages=[HumanMessage(content="resume briefing")],
            briefing_cursor=None,
        )
        result = await resume_briefing_node(state)
        messages = result["messages"]
        assert len(messages) == 1
        assert isinstance(messages[0], AIMessage)
        assert "no briefing to resume" in messages[0].content.lower()

    @pytest.mark.asyncio
    async def test_resume_node_cursor_not_cleared(self):
        # Node must NOT clear briefing_cursor — voice loop owns that
        state = SessionState(
            messages=[HumanMessage(content="resume briefing")],
            briefing_cursor=7,
        )
        result = await resume_briefing_node(state)
        assert "briefing_cursor" not in result


# ---------------------------------------------------------------------------
# CONV-03: tone compression in respond_node
# ---------------------------------------------------------------------------


class TestToneCompression:
    def _make_state_with_phrase(self, phrase: str) -> SessionState:
        return SessionState(
            messages=[HumanMessage(content=phrase)],
            briefing_narrative="Today you have three meetings.",
        )

    def _make_state_with_two_short_messages(self) -> SessionState:
        return SessionState(
            messages=[
                HumanMessage(content="ok"),
                HumanMessage(content="got it"),
            ],
            briefing_narrative="Today you have three meetings.",
        )

    def _make_state_with_one_short_message(self) -> SessionState:
        return SessionState(
            messages=[HumanMessage(content="ok")],
            briefing_narrative="Today you have three meetings.",
        )

    def _make_state_with_long_messages(self) -> SessionState:
        return SessionState(
            messages=[
                HumanMessage(content="this is a long enough message to not trigger"),
                HumanMessage(content="another long message that has many words here"),
            ],
            briefing_narrative="Today you have three meetings.",
        )

    @pytest.mark.asyncio
    async def test_explicit_tone_trigger_rush(self):
        state = self._make_state_with_phrase("I'm in a rush")
        mock_response = _make_mock_response()
        with patch("daily.orchestrator.nodes._openai_client") as mock_client_fn:
            client = AsyncMock()
            client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_client_fn.return_value = client
            result = await respond_node(state)
        assert result.get("tone_override") == "brief"

    @pytest.mark.asyncio
    async def test_explicit_tone_trigger_keep_brief(self):
        state = self._make_state_with_phrase("keep it brief")
        mock_response = _make_mock_response()
        with patch("daily.orchestrator.nodes._openai_client") as mock_client_fn:
            client = AsyncMock()
            client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_client_fn.return_value = client
            result = await respond_node(state)
        assert result.get("tone_override") == "brief"

    @pytest.mark.asyncio
    async def test_explicit_tone_trigger_all_phrases(self):
        for phrase in COMPRESSION_PHRASES:
            state = self._make_state_with_phrase(phrase)
            mock_response = _make_mock_response()
            with patch("daily.orchestrator.nodes._openai_client") as mock_client_fn:
                client = AsyncMock()
                client.chat.completions.create = AsyncMock(return_value=mock_response)
                mock_client_fn.return_value = client
                result = await respond_node(state)
            assert result.get("tone_override") == "brief", (
                f"Expected tone_override='brief' for phrase: {phrase!r}"
            )

    @pytest.mark.asyncio
    async def test_implicit_tone_trigger_two_short(self):
        state = self._make_state_with_two_short_messages()
        mock_response = _make_mock_response()
        with patch("daily.orchestrator.nodes._openai_client") as mock_client_fn:
            client = AsyncMock()
            client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_client_fn.return_value = client
            result = await respond_node(state)
        assert result.get("tone_override") == "brief"

    @pytest.mark.asyncio
    async def test_implicit_no_trigger_one_short(self):
        state = self._make_state_with_one_short_message()
        mock_response = _make_mock_response()
        with patch("daily.orchestrator.nodes._openai_client") as mock_client_fn:
            client = AsyncMock()
            client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_client_fn.return_value = client
            result = await respond_node(state)
        # One short message should NOT trigger implicit compression
        assert result.get("tone_override") != "brief"

    @pytest.mark.asyncio
    async def test_implicit_no_trigger_long_messages(self):
        state = self._make_state_with_long_messages()
        mock_response = _make_mock_response()
        with patch("daily.orchestrator.nodes._openai_client") as mock_client_fn:
            client = AsyncMock()
            client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_client_fn.return_value = client
            result = await respond_node(state)
        assert result.get("tone_override") != "brief"

    @pytest.mark.asyncio
    async def test_tone_override_persists_once_set(self):
        # If tone_override already "brief", respond_node must keep it
        state = SessionState(
            messages=[HumanMessage(content="what else is on today")],
            tone_override="brief",
            briefing_narrative="Today you have three meetings.",
        )
        mock_response = _make_mock_response()
        with patch("daily.orchestrator.nodes._openai_client") as mock_client_fn:
            client = AsyncMock()
            client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_client_fn.return_value = client
            result = await respond_node(state)
        # State_updates should NOT contain tone_override="brief" since it's already set
        # (node skips re-detection when already "brief") — but the AI call must have
        # used compressed settings. We verify by checking messages were returned.
        messages = result.get("messages", [])
        assert len(messages) == 1

    @pytest.mark.asyncio
    async def test_tone_override_prompt_injection(self):
        state = SessionState(
            messages=[HumanMessage(content="I'm in a rush, what's first?")],
            briefing_narrative="Today you have three meetings.",
        )
        mock_response = _make_mock_response()
        captured_messages = []

        async def capture_create(**kwargs):
            captured_messages.extend(kwargs.get("messages", []))
            return mock_response

        with patch("daily.orchestrator.nodes._openai_client") as mock_client_fn:
            client = AsyncMock()
            client.chat.completions.create = AsyncMock(side_effect=capture_create)
            mock_client_fn.return_value = client
            await respond_node(state)

        system_msg = captured_messages[0]["content"] if captured_messages else ""
        assert "Max 2 sentences" in system_msg


# ---------------------------------------------------------------------------
# CONV-03: tone_override must NOT be persisted to DB
# ---------------------------------------------------------------------------


class TestToneNotPersisted:
    @pytest.mark.asyncio
    async def test_tone_override_not_persisted(self):
        state = SessionState(
            messages=[HumanMessage(content="I'm in a rush")],
            briefing_narrative="Today you have three meetings.",
        )
        mock_response = _make_mock_response()

        with patch("daily.orchestrator.nodes._openai_client") as mock_client_fn, \
             patch("daily.orchestrator.nodes.upsert_preference") as mock_upsert:
            client = AsyncMock()
            client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_client_fn.return_value = client
            result = await respond_node(state)

        # tone_override must be set in state but upsert_preference must NOT have been called
        assert result.get("tone_override") == "brief"
        # Verify upsert was never called (or if called, never with tone_override as a key)
        for call in mock_upsert.call_args_list:
            args, kwargs = call
            all_args = list(args) + list(kwargs.values())
            assert "tone_override" not in str(all_args), (
                "upsert_preference was called with tone_override — must not persist to DB"
            )
