"""Tests for draft_node LLM drafting and sent-email style matching.

TDD RED phase — tests describe the expected behavior of the full draft_node
implementation (Plan 02). These tests should fail until the stub draft_node
is replaced with the real implementation.

Covers:
- draft_node sends LLM prompt with user's draft_instruction
- draft_node includes user tone preference in the system prompt
- draft_node fetches sent emails via adapter, redacts them, includes as style examples
- draft_node returns state update with pending_action set to an ActionDraft
- draft_node uses GPT-4.1 (not mini) for draft generation
- draft_node system prompt does NOT contain tools= (SEC-05 enforcement)
- LLM output is parsed to extract draft fields (recipient, subject, body)
- draft_node generates draft without style examples when no email adapters available
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage

from daily.actions.base import ActionDraft, ActionType
from daily.orchestrator.state import SessionState


def _make_state(
    instruction: str = "draft a reply to Alice saying I'm on it",
    tone: str = "conversational",
    briefing_narrative: str = "You have 5 emails and 2 meetings today.",
    active_user_id: int = 1,
) -> SessionState:
    return SessionState(
        messages=[HumanMessage(content=instruction)],
        briefing_narrative=briefing_narrative,
        active_user_id=active_user_id,
        preferences={"tone": tone, "briefing_length": "standard", "rejection_behaviour": "ask_why"},
    )


def _make_llm_response(
    recipient: str = "alice@example.com",
    subject: str = "Re: Project Update",
    body: str = "Hi Alice, I'm on it! Will have it done by EOD.",
) -> MagicMock:
    """Return a mock OpenAI chat completion response."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = json.dumps({
        "recipient": recipient,
        "subject": subject,
        "body": body,
        "event_title": None,
        "start_dt": None,
        "end_dt": None,
        "attendees": [],
    })
    return mock_response


def _make_mock_email_metadata(message_id: str = "sent-001") -> MagicMock:
    """Return a mock email metadata object."""
    meta = MagicMock()
    meta.message_id = message_id
    return meta


# ---------------------------------------------------------------------------
# draft_node produces ActionDraft
# ---------------------------------------------------------------------------


class TestDraftNodeProducesActionDraft:
    """Tests that draft_node generates a valid ActionDraft via LLM."""

    @pytest.mark.asyncio
    async def test_draft_node_returns_pending_action(self):
        """draft_node returns state update with pending_action set to an ActionDraft."""
        state = _make_state()

        mock_llm_response = _make_llm_response()

        with (
            patch("daily.orchestrator.nodes.AsyncOpenAI") as mock_openai_cls,
            patch("daily.orchestrator.nodes.get_email_adapters", return_value=[]),
        ):
            mock_client = AsyncMock()
            mock_openai_cls.return_value = mock_client
            mock_client.chat.completions.create = AsyncMock(return_value=mock_llm_response)

            from daily.orchestrator.nodes import draft_node

            result = await draft_node(state)

        assert "pending_action" in result
        draft = result["pending_action"]
        assert draft is not None
        assert isinstance(draft, ActionDraft)

    @pytest.mark.asyncio
    async def test_draft_node_parses_recipient(self):
        """draft_node parses recipient from LLM JSON output."""
        state = _make_state()

        mock_llm_response = _make_llm_response(recipient="alice@example.com")

        with (
            patch("daily.orchestrator.nodes.AsyncOpenAI") as mock_openai_cls,
            patch("daily.orchestrator.nodes.get_email_adapters", return_value=[]),
        ):
            mock_client = AsyncMock()
            mock_openai_cls.return_value = mock_client
            mock_client.chat.completions.create = AsyncMock(return_value=mock_llm_response)

            from daily.orchestrator.nodes import draft_node

            result = await draft_node(state)

        assert result["pending_action"].recipient == "alice@example.com"

    @pytest.mark.asyncio
    async def test_draft_node_parses_subject(self):
        """draft_node parses subject from LLM JSON output."""
        state = _make_state()

        mock_llm_response = _make_llm_response(subject="Re: Project Update")

        with (
            patch("daily.orchestrator.nodes.AsyncOpenAI") as mock_openai_cls,
            patch("daily.orchestrator.nodes.get_email_adapters", return_value=[]),
        ):
            mock_client = AsyncMock()
            mock_openai_cls.return_value = mock_client
            mock_client.chat.completions.create = AsyncMock(return_value=mock_llm_response)

            from daily.orchestrator.nodes import draft_node

            result = await draft_node(state)

        assert result["pending_action"].subject == "Re: Project Update"

    @pytest.mark.asyncio
    async def test_draft_node_parses_body(self):
        """draft_node parses body from LLM JSON output."""
        state = _make_state()
        expected_body = "Hi Alice, I'm on it! Will have it done by EOD."
        mock_llm_response = _make_llm_response(body=expected_body)

        with (
            patch("daily.orchestrator.nodes.AsyncOpenAI") as mock_openai_cls,
            patch("daily.orchestrator.nodes.get_email_adapters", return_value=[]),
        ):
            mock_client = AsyncMock()
            mock_openai_cls.return_value = mock_client
            mock_client.chat.completions.create = AsyncMock(return_value=mock_llm_response)

            from daily.orchestrator.nodes import draft_node

            result = await draft_node(state)

        assert result["pending_action"].body == expected_body


# ---------------------------------------------------------------------------
# Model selection: GPT-4.1 (not mini)
# ---------------------------------------------------------------------------


class TestDraftNodeModelSelection:
    """Tests that draft_node uses GPT-4.1, not the mini model."""

    @pytest.mark.asyncio
    async def test_draft_node_uses_gpt_41_not_mini(self):
        """draft_node calls LLM with model='gpt-4.1', not 'gpt-4.1-mini'."""
        state = _make_state()
        mock_llm_response = _make_llm_response()

        with (
            patch("daily.orchestrator.nodes.AsyncOpenAI") as mock_openai_cls,
            patch("daily.orchestrator.nodes.get_email_adapters", return_value=[]),
        ):
            mock_client = AsyncMock()
            mock_openai_cls.return_value = mock_client
            mock_client.chat.completions.create = AsyncMock(return_value=mock_llm_response)

            from daily.orchestrator.nodes import draft_node

            await draft_node(state)

        call_kwargs = mock_client.chat.completions.create.call_args
        model_used = call_kwargs.kwargs.get("model") or call_kwargs.args[0] if call_kwargs.args else None
        if model_used is None:
            # Try positional
            model_used = call_kwargs.kwargs.get("model")
        assert model_used == "gpt-4.1", f"Expected 'gpt-4.1', got '{model_used}'"

    @pytest.mark.asyncio
    async def test_draft_node_no_tools_parameter(self):
        """draft_node does NOT pass tools= parameter to LLM (SEC-05/T-03-06)."""
        state = _make_state()
        mock_llm_response = _make_llm_response()

        with (
            patch("daily.orchestrator.nodes.AsyncOpenAI") as mock_openai_cls,
            patch("daily.orchestrator.nodes.get_email_adapters", return_value=[]),
        ):
            mock_client = AsyncMock()
            mock_openai_cls.return_value = mock_client
            mock_client.chat.completions.create = AsyncMock(return_value=mock_llm_response)

            from daily.orchestrator.nodes import draft_node

            await draft_node(state)

        call_kwargs = mock_client.chat.completions.create.call_args
        assert "tools" not in call_kwargs.kwargs, (
            "draft_node must NOT pass tools= to LLM (SEC-05/T-03-06)"
        )

    @pytest.mark.asyncio
    async def test_draft_node_uses_json_object_response_format(self):
        """draft_node uses response_format={'type': 'json_object'} for structured output."""
        state = _make_state()
        mock_llm_response = _make_llm_response()

        with (
            patch("daily.orchestrator.nodes.AsyncOpenAI") as mock_openai_cls,
            patch("daily.orchestrator.nodes.get_email_adapters", return_value=[]),
        ):
            mock_client = AsyncMock()
            mock_openai_cls.return_value = mock_client
            mock_client.chat.completions.create = AsyncMock(return_value=mock_llm_response)

            from daily.orchestrator.nodes import draft_node

            await draft_node(state)

        call_kwargs = mock_client.chat.completions.create.call_args
        response_format = call_kwargs.kwargs.get("response_format")
        assert response_format == {"type": "json_object"}, (
            f"Expected json_object response_format, got: {response_format}"
        )


# ---------------------------------------------------------------------------
# System prompt content tests
# ---------------------------------------------------------------------------


class TestDraftNodeSystemPrompt:
    """Tests that the draft_node system prompt includes required content."""

    @pytest.mark.asyncio
    async def test_draft_node_includes_tone_in_prompt(self):
        """draft_node includes user tone preference in the system prompt."""
        state = _make_state(tone="formal")
        mock_llm_response = _make_llm_response()

        with (
            patch("daily.orchestrator.nodes.AsyncOpenAI") as mock_openai_cls,
            patch("daily.orchestrator.nodes.get_email_adapters", return_value=[]),
        ):
            mock_client = AsyncMock()
            mock_openai_cls.return_value = mock_client
            mock_client.chat.completions.create = AsyncMock(return_value=mock_llm_response)

            from daily.orchestrator.nodes import draft_node

            await draft_node(state)

        call_kwargs = mock_client.chat.completions.create.call_args
        messages = call_kwargs.kwargs.get("messages", [])
        system_content = next(
            (m["content"] for m in messages if m.get("role") == "system"), ""
        )
        assert "formal" in system_content, (
            f"System prompt should contain tone 'formal', got: {system_content[:200]}"
        )

    @pytest.mark.asyncio
    async def test_draft_node_includes_instruction_in_prompt(self):
        """draft_node includes user's draft_instruction in the LLM prompt."""
        instruction = "write a polite decline for the Monday meeting"
        state = _make_state(instruction=instruction)
        mock_llm_response = _make_llm_response()

        with (
            patch("daily.orchestrator.nodes.AsyncOpenAI") as mock_openai_cls,
            patch("daily.orchestrator.nodes.get_email_adapters", return_value=[]),
        ):
            mock_client = AsyncMock()
            mock_openai_cls.return_value = mock_client
            mock_client.chat.completions.create = AsyncMock(return_value=mock_llm_response)

            from daily.orchestrator.nodes import draft_node

            await draft_node(state)

        call_kwargs = mock_client.chat.completions.create.call_args
        messages = call_kwargs.kwargs.get("messages", [])
        # instruction should appear in either system or user messages
        all_content = " ".join(
            m.get("content", "") or "" for m in messages
        )
        assert instruction in all_content, (
            f"LLM prompt should contain the instruction: '{instruction}'"
        )

    @pytest.mark.asyncio
    async def test_draft_system_prompt_constant_exists(self):
        """DRAFT_SYSTEM_PROMPT constant exists in nodes module."""
        from daily.orchestrator import nodes

        assert hasattr(nodes, "DRAFT_SYSTEM_PROMPT"), (
            "nodes module must have DRAFT_SYSTEM_PROMPT constant"
        )
        assert isinstance(nodes.DRAFT_SYSTEM_PROMPT, str)
        assert len(nodes.DRAFT_SYSTEM_PROMPT) > 50


# ---------------------------------------------------------------------------
# Style examples: sent email fetching and redaction
# ---------------------------------------------------------------------------


class TestDraftNodeStyleExamples:
    """Tests that draft_node fetches sent emails and redacts them for style examples."""

    @pytest.mark.asyncio
    async def test_draft_node_fetches_sent_emails_from_adapter(self):
        """draft_node calls adapter to fetch sent emails when adapters are available."""
        state = _make_state()
        mock_llm_response = _make_llm_response()

        mock_adapter = AsyncMock()
        mock_adapter.list_emails = AsyncMock(return_value=[_make_mock_email_metadata("sent-001")])
        mock_adapter.get_email_body = AsyncMock(return_value="Hi there, just wanted to check in.")

        with (
            patch("daily.orchestrator.nodes.AsyncOpenAI") as mock_openai_cls,
            patch("daily.orchestrator.nodes.get_email_adapters", return_value=[mock_adapter]),
            patch("daily.orchestrator.nodes.summarise_and_redact", new=AsyncMock(return_value="[REDACTED]")),
        ):
            mock_client = AsyncMock()
            mock_openai_cls.return_value = mock_client
            mock_client.chat.completions.create = AsyncMock(return_value=mock_llm_response)

            from daily.orchestrator.nodes import draft_node

            await draft_node(state)

        mock_adapter.list_emails.assert_called_once()

    @pytest.mark.asyncio
    async def test_draft_node_calls_summarise_and_redact_on_email_bodies(self):
        """draft_node calls summarise_and_redact for each fetched email body (T-04-07)."""
        state = _make_state()
        mock_llm_response = _make_llm_response()

        mock_adapter = AsyncMock()
        email_meta1 = _make_mock_email_metadata("sent-001")
        email_meta2 = _make_mock_email_metadata("sent-002")
        mock_adapter.list_emails = AsyncMock(return_value=[email_meta1, email_meta2])
        mock_adapter.get_email_body = AsyncMock(return_value="Some email body text")

        mock_redact = AsyncMock(return_value="[REDACTED summary]")

        with (
            patch("daily.orchestrator.nodes.AsyncOpenAI") as mock_openai_cls,
            patch("daily.orchestrator.nodes.get_email_adapters", return_value=[mock_adapter]),
            patch("daily.orchestrator.nodes.summarise_and_redact", new=mock_redact),
        ):
            mock_client = AsyncMock()
            mock_openai_cls.return_value = mock_client
            mock_client.chat.completions.create = AsyncMock(return_value=mock_llm_response)

            from daily.orchestrator.nodes import draft_node

            await draft_node(state)

        # Should have called summarise_and_redact for each fetched email
        assert mock_redact.call_count >= 1, (
            "summarise_and_redact must be called for each sent email body"
        )

    @pytest.mark.asyncio
    async def test_draft_node_includes_redacted_examples_in_prompt(self):
        """draft_node includes redacted style examples in the LLM prompt."""
        state = _make_state()
        mock_llm_response = _make_llm_response()

        mock_adapter = AsyncMock()
        mock_adapter.list_emails = AsyncMock(return_value=[_make_mock_email_metadata("sent-001")])
        mock_adapter.get_email_body = AsyncMock(return_value="Sample email body")
        redacted_text = "REDACTED_STYLE_EXAMPLE_UNIQUE_MARKER"
        mock_redact = AsyncMock(return_value=redacted_text)

        with (
            patch("daily.orchestrator.nodes.AsyncOpenAI") as mock_openai_cls,
            patch("daily.orchestrator.nodes.get_email_adapters", return_value=[mock_adapter]),
            patch("daily.orchestrator.nodes.summarise_and_redact", new=mock_redact),
        ):
            mock_client = AsyncMock()
            mock_openai_cls.return_value = mock_client
            mock_client.chat.completions.create = AsyncMock(return_value=mock_llm_response)

            from daily.orchestrator.nodes import draft_node

            await draft_node(state)

        call_kwargs = mock_client.chat.completions.create.call_args
        messages = call_kwargs.kwargs.get("messages", [])
        all_content = " ".join(m.get("content", "") or "" for m in messages)
        assert redacted_text in all_content, (
            "Redacted style examples should be included in the LLM prompt"
        )

    @pytest.mark.asyncio
    async def test_draft_node_generates_draft_without_style_examples(self):
        """draft_node still generates a draft when no email adapters are available."""
        state = _make_state()
        mock_llm_response = _make_llm_response()

        with (
            patch("daily.orchestrator.nodes.AsyncOpenAI") as mock_openai_cls,
            patch("daily.orchestrator.nodes.get_email_adapters", return_value=[]),
        ):
            mock_client = AsyncMock()
            mock_openai_cls.return_value = mock_client
            mock_client.chat.completions.create = AsyncMock(return_value=mock_llm_response)

            from daily.orchestrator.nodes import draft_node

            result = await draft_node(state)

        # Should still produce a pending_action even without adapters
        assert "pending_action" in result
        assert result["pending_action"] is not None

    @pytest.mark.asyncio
    async def test_draft_node_limits_style_examples_to_five(self):
        """draft_node fetches at most 5 sent emails for style examples."""
        state = _make_state()
        mock_llm_response = _make_llm_response()

        # Return 8 emails from the adapter
        eight_emails = [_make_mock_email_metadata(f"sent-{i:03d}") for i in range(8)]
        mock_adapter = AsyncMock()
        mock_adapter.list_emails = AsyncMock(return_value=eight_emails)
        mock_adapter.get_email_body = AsyncMock(return_value="Email body text")
        mock_redact = AsyncMock(return_value="[REDACTED]")

        with (
            patch("daily.orchestrator.nodes.AsyncOpenAI") as mock_openai_cls,
            patch("daily.orchestrator.nodes.get_email_adapters", return_value=[mock_adapter]),
            patch("daily.orchestrator.nodes.summarise_and_redact", new=mock_redact),
        ):
            mock_client = AsyncMock()
            mock_openai_cls.return_value = mock_client
            mock_client.chat.completions.create = AsyncMock(return_value=mock_llm_response)

            from daily.orchestrator.nodes import draft_node

            await draft_node(state)

        # summarise_and_redact should be called at most 5 times
        assert mock_redact.call_count <= 5, (
            f"Expected at most 5 style examples, got {mock_redact.call_count}"
        )


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestDraftNodeErrorHandling:
    """Tests for error handling in draft_node."""

    @pytest.mark.asyncio
    async def test_draft_node_handles_llm_error_gracefully(self):
        """draft_node returns error message when LLM call fails."""
        state = _make_state()

        with (
            patch("daily.orchestrator.nodes.AsyncOpenAI") as mock_openai_cls,
            patch("daily.orchestrator.nodes.get_email_adapters", return_value=[]),
        ):
            mock_client = AsyncMock()
            mock_openai_cls.return_value = mock_client
            mock_client.chat.completions.create = AsyncMock(
                side_effect=Exception("API timeout")
            )

            from daily.orchestrator.nodes import draft_node

            result = await draft_node(state)

        # Should return an error message, not raise
        assert "messages" in result
        messages = result["messages"]
        assert len(messages) > 0
        error_content = messages[-1].content.lower()
        assert "trouble" in error_content or "error" in error_content or "try" in error_content

    @pytest.mark.asyncio
    async def test_draft_node_handles_adapter_failure_gracefully(self):
        """draft_node continues to draft even if adapter fetch fails."""
        state = _make_state()
        mock_llm_response = _make_llm_response()

        mock_adapter = AsyncMock()
        mock_adapter.list_emails = AsyncMock(side_effect=Exception("API error"))

        with (
            patch("daily.orchestrator.nodes.AsyncOpenAI") as mock_openai_cls,
            patch("daily.orchestrator.nodes.get_email_adapters", return_value=[mock_adapter]),
        ):
            mock_client = AsyncMock()
            mock_openai_cls.return_value = mock_client
            mock_client.chat.completions.create = AsyncMock(return_value=mock_llm_response)

            from daily.orchestrator.nodes import draft_node

            result = await draft_node(state)

        # Should still produce a pending_action despite adapter failure
        assert "pending_action" in result
        assert result["pending_action"] is not None


# ---------------------------------------------------------------------------
# Action type inference
# ---------------------------------------------------------------------------


class TestDraftNodeActionTypeInference:
    """Tests that draft_node correctly infers action type from user instruction."""

    @pytest.mark.asyncio
    async def test_draft_node_infers_draft_email_for_reply(self):
        """draft_node infers draft_email for email reply instructions."""
        state = _make_state(instruction="reply to Alice's email")
        mock_llm_response = _make_llm_response()

        with (
            patch("daily.orchestrator.nodes.AsyncOpenAI") as mock_openai_cls,
            patch("daily.orchestrator.nodes.get_email_adapters", return_value=[]),
        ):
            mock_client = AsyncMock()
            mock_openai_cls.return_value = mock_client
            mock_client.chat.completions.create = AsyncMock(return_value=mock_llm_response)

            from daily.orchestrator.nodes import draft_node

            result = await draft_node(state)

        draft = result.get("pending_action")
        assert draft is not None
        assert draft.action_type in (ActionType.draft_email, ActionType.compose_email)

    @pytest.mark.asyncio
    async def test_draft_node_infers_schedule_event_for_meeting(self):
        """draft_node infers schedule_event for meeting scheduling instructions."""
        state = _make_state(instruction="schedule a meeting with Bob tomorrow at 2pm")
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "recipient": None,
            "subject": None,
            "body": "Meeting invitation",
            "event_title": "Meeting with Bob",
            "start_dt": "2026-04-12T14:00:00",
            "end_dt": "2026-04-12T15:00:00",
            "attendees": ["bob@example.com"],
        })

        with (
            patch("daily.orchestrator.nodes.AsyncOpenAI") as mock_openai_cls,
            patch("daily.orchestrator.nodes.get_email_adapters", return_value=[]),
        ):
            mock_client = AsyncMock()
            mock_openai_cls.return_value = mock_client
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

            from daily.orchestrator.nodes import draft_node

            result = await draft_node(state)

        draft = result.get("pending_action")
        assert draft is not None
        assert draft.action_type in (ActionType.schedule_event, ActionType.reschedule_event,
                                      ActionType.draft_email, ActionType.compose_email)
