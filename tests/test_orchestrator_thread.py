"""Tests for orchestrator node functions (Task 2 TDD).

Tests cover:
- respond_node: GPT-4.1 mini, response_format=json_object, OrchestratorIntent validation
- summarise_thread_node: GPT-4.1, adapter registry, summarise_and_redact, SEC-04 raw body
- Signal capture via asyncio.create_task()
- No-adapters fallback message
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_openai_response(action: str, narrative: str, target_id: str | None = None):
    """Return a mock OpenAI chat completion response with OrchestratorIntent JSON."""
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = json.dumps({
        "action": action,
        "narrative": narrative,
        "target_id": target_id,
    })
    return mock_resp


def _make_state(
    messages=None,
    briefing_narrative="Test briefing",
    active_user_id=1,
    preferences=None,
    email_context=None,
):
    """Create a SessionState for testing."""
    from daily.orchestrator.state import SessionState

    return SessionState(
        messages=messages or [HumanMessage(content="What emails do I have?")],
        briefing_narrative=briefing_narrative,
        active_user_id=active_user_id,
        preferences=preferences or {"tone": "conversational", "briefing_length": "standard"},
        email_context=email_context or [],
    )


# ---------------------------------------------------------------------------
# respond_node tests
# ---------------------------------------------------------------------------


class TestRespondNode:
    @pytest.mark.asyncio
    async def test_respond_node_returns_ai_message(self):
        """respond_node returns AIMessage containing narrative from OrchestratorIntent."""
        from langchain_core.messages import AIMessage

        from daily.orchestrator.nodes import respond_node

        mock_response = _make_openai_response("answer", "You have 5 emails today.")

        with patch("daily.orchestrator.nodes.AsyncOpenAI") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await respond_node(_make_state())

        messages = result.get("messages", [])
        assert len(messages) == 1
        assert isinstance(messages[0], AIMessage)
        assert messages[0].content == "You have 5 emails today."

    @pytest.mark.asyncio
    async def test_respond_node_uses_gpt_4_1_mini(self):
        """respond_node calls GPT-4.1 mini (D-02 — mini for quick follow-ups)."""
        from daily.orchestrator.nodes import respond_node

        mock_response = _make_openai_response("answer", "Response text.")

        with patch("daily.orchestrator.nodes.AsyncOpenAI") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            await respond_node(_make_state())

            call_kwargs = mock_client.chat.completions.create.call_args[1]
            assert call_kwargs.get("model") == "gpt-4.1-mini"

    @pytest.mark.asyncio
    async def test_respond_node_uses_response_format_json_object(self):
        """respond_node uses response_format=json_object (SEC-05)."""
        from daily.orchestrator.nodes import respond_node

        mock_response = _make_openai_response("answer", "Response.")

        with patch("daily.orchestrator.nodes.AsyncOpenAI") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            await respond_node(_make_state())

            call_kwargs = mock_client.chat.completions.create.call_args[1]
            assert call_kwargs.get("response_format") == {"type": "json_object"}

    @pytest.mark.asyncio
    async def test_respond_node_includes_briefing_narrative_in_prompt(self):
        """respond_node includes briefing_narrative in system prompt context."""
        from daily.orchestrator.nodes import respond_node

        mock_response = _make_openai_response("answer", "Answer.")
        state = _make_state(briefing_narrative="Important morning briefing content")

        with patch("daily.orchestrator.nodes.AsyncOpenAI") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            await respond_node(state)

            call_kwargs = mock_client.chat.completions.create.call_args[1]
            messages = call_kwargs["messages"]
            system_msg = messages[0]
            assert system_msg["role"] == "system"
            assert "Important morning briefing content" in system_msg["content"]

    @pytest.mark.asyncio
    async def test_respond_node_validates_llm_output_as_orchestrator_intent(self):
        """respond_node validates LLM output as OrchestratorIntent (SEC-05 D-03)."""
        from daily.orchestrator.nodes import respond_node

        # Valid OrchestratorIntent JSON
        mock_response = _make_openai_response("answer", "Validated response.")

        with patch("daily.orchestrator.nodes.AsyncOpenAI") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await respond_node(_make_state())

        # Should succeed and return the narrative
        assert result["messages"][0].content == "Validated response."

    @pytest.mark.asyncio
    async def test_respond_node_returns_fallback_on_invalid_intent(self):
        """respond_node returns fallback message when LLM output is invalid JSON."""
        from daily.orchestrator.nodes import respond_node

        # Respond with invalid JSON (missing 'action' key)
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].message.content = '{"narrative": "missing action field"}'

        with patch("daily.orchestrator.nodes.AsyncOpenAI") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)
            mock_client_class.return_value = mock_client

            result = await respond_node(_make_state())

        # Should fall back gracefully
        content = result["messages"][0].content
        assert "couldn't process" in content.lower() or "rephrase" in content.lower()

    @pytest.mark.asyncio
    async def test_respond_node_does_not_use_tools_parameter(self):
        """respond_node must NOT pass tools= to LLM (SEC-05/T-03-06).

        Verifies by checking the actual call arguments, not just source text
        (docstrings may mention 'tools=' as security notes).
        """
        from daily.orchestrator.nodes import respond_node

        mock_response = _make_openai_response("answer", "Response.")

        with patch("daily.orchestrator.nodes.AsyncOpenAI") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            await respond_node(_make_state())

            call_kwargs = mock_client.chat.completions.create.call_args[1]
            assert "tools" not in call_kwargs

    @pytest.mark.asyncio
    async def test_respond_node_creates_follow_up_signal_task(self):
        """respond_node captures follow_up signal via asyncio.create_task (D-08)."""
        from daily.orchestrator.nodes import respond_node

        mock_response = _make_openai_response("answer", "Response.")

        captured_tasks = []

        def mock_create_task(coro):
            captured_tasks.append(coro)
            # Return a mock future so asyncio doesn't complain
            future = asyncio.get_event_loop().create_future()
            future.set_result(None)
            return future

        with patch("daily.orchestrator.nodes.AsyncOpenAI") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            with patch("daily.orchestrator.nodes.asyncio.create_task", side_effect=mock_create_task):
                await respond_node(_make_state(active_user_id=1))

        # Should have created at least one task for signal capture
        assert len(captured_tasks) >= 1


# ---------------------------------------------------------------------------
# summarise_thread_node tests
# ---------------------------------------------------------------------------


class TestSummariseThreadNode:
    @pytest.mark.asyncio
    async def test_summarise_thread_node_fetches_body_via_adapter(self):
        """summarise_thread_node fetches email body via adapter registry."""
        from daily.orchestrator.nodes import summarise_thread_node
        from daily.orchestrator.session import set_email_adapters

        mock_adapter = AsyncMock()
        mock_adapter.get_email_body = AsyncMock(return_value="Raw email body text")
        set_email_adapters([mock_adapter])

        mock_openai_resp = _make_openai_response("summarise_thread", "Email summary.")

        with patch("daily.orchestrator.nodes.AsyncOpenAI") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_openai_resp)
            mock_client_class.return_value = mock_client

            with patch("daily.orchestrator.nodes.summarise_and_redact", new_callable=AsyncMock) as mock_redact:
                mock_redact.return_value = "Redacted summary"

                state = _make_state(messages=[HumanMessage(content="Summarise that email thread")])
                result = await summarise_thread_node(state)

        mock_adapter.get_email_body.assert_called_once()

    @pytest.mark.asyncio
    async def test_summarise_thread_node_calls_gpt_4_1(self):
        """summarise_thread_node uses GPT-4.1 (D-02 — full model for reasoning)."""
        from daily.orchestrator.nodes import summarise_thread_node
        from daily.orchestrator.session import set_email_adapters

        mock_adapter = AsyncMock()
        mock_adapter.get_email_body = AsyncMock(return_value="Email content")
        set_email_adapters([mock_adapter])

        mock_openai_resp = _make_openai_response("summarise_thread", "Summary.")

        with patch("daily.orchestrator.nodes.AsyncOpenAI") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_openai_resp)
            mock_client_class.return_value = mock_client

            with patch("daily.orchestrator.nodes.summarise_and_redact", new_callable=AsyncMock) as mock_redact:
                mock_redact.return_value = "Redacted"

                await summarise_thread_node(_make_state())

            # The last call to create should be with gpt-4.1
            calls = mock_client.chat.completions.create.call_args_list
            # Find the call with gpt-4.1 (not mini)
            models_used = [c[1].get("model") for c in calls]
            assert "gpt-4.1" in models_used

    @pytest.mark.asyncio
    async def test_summarise_thread_node_calls_summarise_and_redact(self):
        """summarise_thread_node passes raw body through summarise_and_redact (SEC-02)."""
        from daily.orchestrator.nodes import summarise_thread_node
        from daily.orchestrator.session import set_email_adapters

        mock_adapter = AsyncMock()
        mock_adapter.get_email_body = AsyncMock(return_value="Raw email content here")
        set_email_adapters([mock_adapter])

        mock_openai_resp = _make_openai_response("summarise_thread", "Summary.")

        with patch("daily.orchestrator.nodes.AsyncOpenAI") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_openai_resp)
            mock_client_class.return_value = mock_client

            with patch("daily.orchestrator.nodes.summarise_and_redact", new_callable=AsyncMock) as mock_redact:
                mock_redact.return_value = "Redacted summary"

                await summarise_thread_node(_make_state())

            mock_redact.assert_called_once()
            # First arg is the raw body
            call_args = mock_redact.call_args
            assert call_args[0][0] == "Raw email content here"

    @pytest.mark.asyncio
    async def test_summarise_thread_node_raw_body_not_in_returned_state(self):
        """Raw email body must NOT appear in returned state (SEC-04/T-03-07)."""
        from daily.orchestrator.nodes import summarise_thread_node
        from daily.orchestrator.session import set_email_adapters

        raw_body = "SENSITIVE: password=secret123, account details, private info"
        mock_adapter = AsyncMock()
        mock_adapter.get_email_body = AsyncMock(return_value=raw_body)
        set_email_adapters([mock_adapter])

        mock_openai_resp = _make_openai_response("summarise_thread", "Clean summary.")

        with patch("daily.orchestrator.nodes.AsyncOpenAI") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_openai_resp)
            mock_client_class.return_value = mock_client

            with patch("daily.orchestrator.nodes.summarise_and_redact", new_callable=AsyncMock) as mock_redact:
                mock_redact.return_value = "Redacted summary without sensitive info"

                result = await summarise_thread_node(_make_state())

        # Verify raw body is NOT anywhere in the returned state
        result_str = str(result)
        assert "SENSITIVE" not in result_str
        assert "password=secret123" not in result_str
        assert "private info" not in result_str

    @pytest.mark.asyncio
    async def test_summarise_thread_node_returns_summary_in_ai_message(self):
        """summarise_thread_node returns summary in AIMessage."""
        from langchain_core.messages import AIMessage

        from daily.orchestrator.nodes import summarise_thread_node
        from daily.orchestrator.session import set_email_adapters

        mock_adapter = AsyncMock()
        mock_adapter.get_email_body = AsyncMock(return_value="Email body")
        set_email_adapters([mock_adapter])

        mock_openai_resp = _make_openai_response("summarise_thread", "Here is the summary of the thread.")

        with patch("daily.orchestrator.nodes.AsyncOpenAI") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_openai_resp)
            mock_client_class.return_value = mock_client

            with patch("daily.orchestrator.nodes.summarise_and_redact", new_callable=AsyncMock) as mock_redact:
                mock_redact.return_value = "Redacted"

                result = await summarise_thread_node(_make_state())

        messages = result.get("messages", [])
        assert len(messages) == 1
        assert isinstance(messages[0], AIMessage)
        assert "summary" in messages[0].content.lower() or "thread" in messages[0].content.lower()

    @pytest.mark.asyncio
    async def test_summarise_thread_node_returns_no_adapters_message(self):
        """summarise_thread_node returns helpful message when no adapters registered."""
        from daily.orchestrator.nodes import summarise_thread_node
        from daily.orchestrator.session import set_email_adapters

        set_email_adapters([])

        result = await summarise_thread_node(_make_state())

        messages = result.get("messages", [])
        assert len(messages) == 1
        content = messages[0].content.lower()
        assert "connect" in content or "no email" in content

    @pytest.mark.asyncio
    async def test_summarise_thread_node_captures_expand_signal(self):
        """summarise_thread_node fires expand signal via asyncio.create_task (D-08)."""
        from daily.orchestrator.nodes import summarise_thread_node
        from daily.orchestrator.session import set_email_adapters

        mock_adapter = AsyncMock()
        mock_adapter.get_email_body = AsyncMock(return_value="Body")
        set_email_adapters([mock_adapter])

        mock_openai_resp = _make_openai_response("summarise_thread", "Summary.")

        captured_tasks = []

        def mock_create_task(coro):
            captured_tasks.append(coro)
            future = asyncio.get_event_loop().create_future()
            future.set_result(None)
            return future

        with patch("daily.orchestrator.nodes.AsyncOpenAI") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_openai_resp)
            mock_client_class.return_value = mock_client

            with patch("daily.orchestrator.nodes.summarise_and_redact", new_callable=AsyncMock) as mock_redact:
                mock_redact.return_value = "Redacted"

                with patch("daily.orchestrator.nodes.asyncio.create_task", side_effect=mock_create_task):
                    await summarise_thread_node(_make_state(active_user_id=1))

        assert len(captured_tasks) >= 1

    @pytest.mark.asyncio
    async def test_summarise_thread_node_does_not_use_tools_parameter(self):
        """summarise_thread_node must NOT pass tools= to LLM (SEC-05/T-03-06).

        Verifies by checking actual call arguments (docstrings may reference 'tools=').
        """
        from daily.orchestrator.nodes import summarise_thread_node
        from daily.orchestrator.session import set_email_adapters

        mock_adapter = AsyncMock()
        mock_adapter.get_email_body = AsyncMock(return_value="Body")
        set_email_adapters([mock_adapter])

        mock_openai_resp = _make_openai_response("summarise_thread", "Summary.")

        with patch("daily.orchestrator.nodes.AsyncOpenAI") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_openai_resp)
            mock_client_class.return_value = mock_client

            with patch("daily.orchestrator.nodes.summarise_and_redact", new_callable=AsyncMock) as mock_redact:
                mock_redact.return_value = "Redacted"
                await summarise_thread_node(_make_state())

            for call in mock_client.chat.completions.create.call_args_list:
                call_kwargs = call[1]
                assert "tools" not in call_kwargs

    @pytest.mark.asyncio
    async def test_summarise_thread_node_uses_orchestrator_intent_validation(self):
        """summarise_thread_node validates LLM output via OrchestratorIntent (D-03)."""
        import inspect

        from daily.orchestrator import nodes

        source = inspect.getsource(nodes.summarise_thread_node)
        assert "model_validate_json" in source or "OrchestratorIntent" in source


# ---------------------------------------------------------------------------
# email_context resolution tests (FIX-03)
# ---------------------------------------------------------------------------

SAMPLE_EMAIL_CONTEXT = [
    {
        "message_id": "msg_001",
        "thread_id": "thread_001",
        "subject": "Quarterly Report Q1",
        "sender": "Alice Johnson <alice@example.com>",
        "recipient": "user@example.com",
        "timestamp": "2026-04-16T09:00:00",
    },
    {
        "message_id": "msg_002",
        "thread_id": "thread_002",
        "subject": "Team Standup Notes",
        "sender": "Bob Smith <bob@example.com>",
        "recipient": "user@example.com",
        "timestamp": "2026-04-16T10:00:00",
    },
]


class TestSummariseThreadNodeResolution:
    """Tests for message_id resolution from email_context (FIX-03)."""

    @pytest.mark.asyncio
    async def test_resolves_message_id_from_subject_match(self):
        """summarise_thread_node resolves message_id from email_context when user message
        matches a subject — adapter.get_email_body called with the matching email's
        message_id, NOT the user's raw message text."""
        from daily.orchestrator.nodes import summarise_thread_node
        from daily.orchestrator.session import set_email_adapters

        mock_adapter = AsyncMock()
        mock_adapter.get_email_body = AsyncMock(return_value="Email body content")
        set_email_adapters([mock_adapter])

        mock_openai_resp = _make_openai_response("summarise_thread", "Summary of quarterly report.")

        with patch("daily.orchestrator.nodes.AsyncOpenAI") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_openai_resp)
            mock_client_class.return_value = mock_client

            with patch("daily.orchestrator.nodes.summarise_and_redact", new_callable=AsyncMock) as mock_redact:
                mock_redact.return_value = "Redacted content"

                state = _make_state(
                    messages=[HumanMessage(content="Tell me about the quarterly report")],
                    email_context=SAMPLE_EMAIL_CONTEXT,
                )
                await summarise_thread_node(state)

        mock_adapter.get_email_body.assert_called_once_with("msg_001")

    @pytest.mark.asyncio
    async def test_resolves_message_id_from_sender_match(self):
        """summarise_thread_node resolves message_id when user message matches a sender
        name — adapter.get_email_body called with the matching email's message_id."""
        from daily.orchestrator.nodes import summarise_thread_node
        from daily.orchestrator.session import set_email_adapters

        mock_adapter = AsyncMock()
        mock_adapter.get_email_body = AsyncMock(return_value="Email body content")
        set_email_adapters([mock_adapter])

        mock_openai_resp = _make_openai_response("summarise_thread", "Summary from Alice.")

        with patch("daily.orchestrator.nodes.AsyncOpenAI") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_openai_resp)
            mock_client_class.return_value = mock_client

            with patch("daily.orchestrator.nodes.summarise_and_redact", new_callable=AsyncMock) as mock_redact:
                mock_redact.return_value = "Redacted content"

                state = _make_state(
                    messages=[HumanMessage(content="What did Alice say?")],
                    email_context=SAMPLE_EMAIL_CONTEXT,
                )
                await summarise_thread_node(state)

        mock_adapter.get_email_body.assert_called_once_with("msg_001")

    @pytest.mark.asyncio
    async def test_empty_email_context_returns_error(self):
        """summarise_thread_node returns user-friendly error when email_context is empty."""
        from daily.orchestrator.nodes import summarise_thread_node
        from daily.orchestrator.session import set_email_adapters

        mock_adapter = AsyncMock()
        set_email_adapters([mock_adapter])

        state = _make_state(
            messages=[HumanMessage(content="Summarise that email")],
            email_context=[],
        )
        result = await summarise_thread_node(state)

        messages = result.get("messages", [])
        assert len(messages) == 1
        assert "I can't find that email" in messages[0].content

    @pytest.mark.asyncio
    async def test_no_match_returns_error(self):
        """summarise_thread_node returns user-friendly error when no email in
        email_context matches the user's request."""
        from daily.orchestrator.nodes import summarise_thread_node
        from daily.orchestrator.session import set_email_adapters

        mock_adapter = AsyncMock()
        set_email_adapters([mock_adapter])

        state = _make_state(
            messages=[HumanMessage(content="Tell me about the budget proposal")],
            email_context=SAMPLE_EMAIL_CONTEXT,
        )
        result = await summarise_thread_node(state)

        messages = result.get("messages", [])
        assert len(messages) == 1
        assert "I can't find that email" in messages[0].content

    @pytest.mark.asyncio
    async def test_case_insensitive_matching(self):
        """summarise_thread_node matching is case-insensitive — uppercase user query
        matches email subject with mixed case."""
        from daily.orchestrator.nodes import summarise_thread_node
        from daily.orchestrator.session import set_email_adapters

        mock_adapter = AsyncMock()
        mock_adapter.get_email_body = AsyncMock(return_value="Email body content")
        set_email_adapters([mock_adapter])

        mock_openai_resp = _make_openai_response("summarise_thread", "Summary.")

        with patch("daily.orchestrator.nodes.AsyncOpenAI") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_openai_resp)
            mock_client_class.return_value = mock_client

            with patch("daily.orchestrator.nodes.summarise_and_redact", new_callable=AsyncMock) as mock_redact:
                mock_redact.return_value = "Redacted content"

                state = _make_state(
                    messages=[HumanMessage(content="QUARTERLY REPORT")],
                    email_context=SAMPLE_EMAIL_CONTEXT,
                )
                await summarise_thread_node(state)

        mock_adapter.get_email_body.assert_called_once_with("msg_001")
