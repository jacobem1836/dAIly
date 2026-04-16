"""Tests for _capture_signal sender metadata (Plan 08-02).

Covers:
- _capture_signal with sender stores normalised metadata_json
- _capture_signal without sender stores null metadata (backward-compat)
- _capture_signal normalises sender: lowercase + strip
- summarise_thread_node passes sender from email_context to _capture_signal
- summarise_thread_node falls back to None sender when message_id not matched
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_session_ctx():
    """Return an async context manager mock for async_session."""
    mock_session = AsyncMock()
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    return mock_ctx, mock_session


def _make_two_step_llm_responses(message_id: str = "m1"):
    """Return (identify_resp, summarise_resp) mock OpenAI responses."""
    identify_resp = MagicMock()
    identify_resp.choices = [MagicMock()]
    identify_resp.choices[0].message.content = json.dumps({
        "action": "summarise_thread",
        "narrative": "",
        "target_id": message_id,
    })

    summarise_resp = MagicMock()
    summarise_resp.choices = [MagicMock()]
    summarise_resp.choices[0].message.content = json.dumps({
        "action": "summarise_thread",
        "narrative": "Thread summary.",
        "target_id": message_id,
    })

    return identify_resp, summarise_resp


# ---------------------------------------------------------------------------
# _capture_signal tests
# ---------------------------------------------------------------------------

class TestCaptureSignalSenderMetadata:
    @pytest.mark.asyncio
    async def test_capture_signal_with_sender_stores_metadata(self):
        """_capture_signal with sender= stores normalised metadata_json."""
        from daily.orchestrator.nodes import _capture_signal
        from daily.profile.signals import SignalType

        mock_ctx, mock_session = _make_mock_session_ctx()
        captured_calls = []

        async def fake_append_signal(**kwargs):
            captured_calls.append(kwargs)

        with patch("daily.db.engine.async_session", return_value=mock_ctx):
            with patch("daily.profile.signals.append_signal", side_effect=fake_append_signal):
                await _capture_signal(
                    user_id=1,
                    signal_type=SignalType.expand,
                    target_id="msg-abc",
                    sender="Alice@Example.com",
                )

        assert len(captured_calls) == 1
        assert captured_calls[0]["metadata"] == {"sender": "alice@example.com"}

    @pytest.mark.asyncio
    async def test_capture_signal_without_sender_stores_null_metadata(self):
        """_capture_signal without sender= stores null metadata (backward-compat for follow_up)."""
        from daily.orchestrator.nodes import _capture_signal
        from daily.profile.signals import SignalType

        mock_ctx, mock_session = _make_mock_session_ctx()
        captured_calls = []

        async def fake_append_signal(**kwargs):
            captured_calls.append(kwargs)

        with patch("daily.db.engine.async_session", return_value=mock_ctx):
            with patch("daily.profile.signals.append_signal", side_effect=fake_append_signal):
                await _capture_signal(
                    user_id=1,
                    signal_type=SignalType.follow_up,
                )

        assert len(captured_calls) == 1
        assert captured_calls[0]["metadata"] is None

    @pytest.mark.asyncio
    async def test_capture_signal_normalises_sender_lowercase_strip(self):
        """_capture_signal normalises sender: lowercase + strip whitespace."""
        from daily.orchestrator.nodes import _capture_signal
        from daily.profile.signals import SignalType

        mock_ctx, mock_session = _make_mock_session_ctx()
        captured_calls = []

        async def fake_append_signal(**kwargs):
            captured_calls.append(kwargs)

        with patch("daily.db.engine.async_session", return_value=mock_ctx):
            with patch("daily.profile.signals.append_signal", side_effect=fake_append_signal):
                await _capture_signal(
                    user_id=1,
                    signal_type=SignalType.expand,
                    sender="  BOB@EXAMPLE.COM  ",
                )

        assert captured_calls[0]["metadata"] == {"sender": "bob@example.com"}


# ---------------------------------------------------------------------------
# summarise_thread_node sender propagation tests
# ---------------------------------------------------------------------------

class TestSummariseThreadSenderCapture:
    @pytest.mark.asyncio
    async def test_summarise_thread_captures_expand_with_sender(self):
        """summarise_thread_node passes sender from email_context to _capture_signal."""
        from daily.orchestrator.nodes import summarise_thread_node
        from daily.orchestrator.state import SessionState

        mock_adapter = AsyncMock()
        mock_adapter.get_email_body = AsyncMock(return_value="Email body content")

        identify_resp, summarise_resp = _make_two_step_llm_responses(message_id="m1")
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=[identify_resp, summarise_resp]
        )

        email_context = [
            {
                "message_id": "m1",
                "thread_id": "t1",
                "subject": "Important Project",
                "sender": "bob@example.com",
            }
        ]

        state = SessionState(
            messages=[HumanMessage(content="Summarise the project email")],
            briefing_narrative="Test briefing",
            active_user_id=1,
            preferences={},
            email_context=email_context,
        )

        captured_signal_calls = []

        async def fake_capture_signal(user_id, signal_type, target_id=None, sender=None):
            captured_signal_calls.append({
                "user_id": user_id,
                "signal_type": signal_type,
                "target_id": target_id,
                "sender": sender,
            })

        captured_coros = []

        def mock_create_task(coro):
            captured_coros.append(coro)
            future = asyncio.get_event_loop().create_future()
            future.set_result(None)
            return future

        with patch("daily.orchestrator.nodes._openai_client", return_value=mock_client):
            with patch("daily.orchestrator.nodes.get_email_adapters", return_value=[mock_adapter]):
                with patch("daily.orchestrator.nodes.summarise_and_redact", new_callable=AsyncMock) as mock_redact:
                    mock_redact.return_value = "Redacted content"
                    with patch("daily.orchestrator.nodes._capture_signal", side_effect=fake_capture_signal):
                        with patch("daily.orchestrator.nodes.asyncio.create_task", side_effect=mock_create_task):
                            await summarise_thread_node(state)

        # Run captured coroutines
        for coro in captured_coros:
            await coro

        assert len(captured_signal_calls) >= 1
        expand_call = captured_signal_calls[0]
        assert expand_call.get("sender") == "bob@example.com"

    @pytest.mark.asyncio
    async def test_summarise_thread_unknown_message_id_captures_null_sender(self):
        """When message_id has no match in email_context, sender falls back to None."""
        from daily.orchestrator.nodes import summarise_thread_node
        from daily.orchestrator.state import SessionState

        mock_adapter = AsyncMock()
        mock_adapter.get_email_body = AsyncMock(return_value="Email body content")

        # LLM identifies "m-unknown" which is NOT in email_context
        identify_resp = MagicMock()
        identify_resp.choices = [MagicMock()]
        identify_resp.choices[0].message.content = json.dumps({
            "action": "summarise_thread",
            "narrative": "",
            "target_id": "m-unknown",
        })
        summarise_resp = MagicMock()
        summarise_resp.choices = [MagicMock()]
        summarise_resp.choices[0].message.content = json.dumps({
            "action": "summarise_thread",
            "narrative": "Summary.",
            "target_id": "m-unknown",
        })

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=[identify_resp, summarise_resp]
        )

        email_context = [
            {
                "message_id": "m1",
                "thread_id": "t1",
                "subject": "Something else",
                "sender": "alice@example.com",
            }
        ]

        state = SessionState(
            messages=[HumanMessage(content="Summarise that email")],
            briefing_narrative="Test briefing",
            active_user_id=1,
            preferences={},
            email_context=email_context,
        )

        captured_signal_calls = []

        async def fake_capture_signal(user_id, signal_type, target_id=None, sender=None):
            captured_signal_calls.append({
                "user_id": user_id,
                "signal_type": signal_type,
                "target_id": target_id,
                "sender": sender,
            })

        captured_coros = []

        def mock_create_task(coro):
            captured_coros.append(coro)
            future = asyncio.get_event_loop().create_future()
            future.set_result(None)
            return future

        with patch("daily.orchestrator.nodes._openai_client", return_value=mock_client):
            with patch("daily.orchestrator.nodes.get_email_adapters", return_value=[mock_adapter]):
                with patch("daily.orchestrator.nodes.summarise_and_redact", new_callable=AsyncMock) as mock_redact:
                    mock_redact.return_value = "Redacted content"
                    with patch("daily.orchestrator.nodes._capture_signal", side_effect=fake_capture_signal):
                        with patch("daily.orchestrator.nodes.asyncio.create_task", side_effect=mock_create_task):
                            await summarise_thread_node(state)

        for coro in captured_coros:
            await coro

        assert len(captured_signal_calls) >= 1
        expand_call = captured_signal_calls[0]
        assert expand_call.get("sender") is None
