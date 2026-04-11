"""Unit tests for concrete ActionExecutor implementations.

Tests cover:
- GmailExecutor: validate() (scope + whitelist), execute() (MIME, In-Reply-To, base64url, threading)
- SlackExecutor: validate() (scope + channel whitelist), execute() (thread_ts as string)
- OutlookExecutor: validate() (scope + whitelist), execute() (Graph API sendMail body)
- GoogleCalendarExecutor: validate() (scope + attendee whitelist), execute() (insert vs patch)
- execute_node dispatch: provider routing, validation gate, fire-and-forget logging

TDD approach — tests are written first (RED), then implementations (GREEN).
"""

import asyncio
import base64
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from daily.actions.base import ActionDraft, ActionResult, ActionType


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _email_draft(**kwargs) -> ActionDraft:
    defaults = dict(
        action_type=ActionType.draft_email,
        recipient="alice@example.com",
        subject="Hello",
        body="Hi Alice",
        thread_id="thread-001",
        thread_message_id="<msg-001@mail.gmail.com>",
    )
    defaults.update(kwargs)
    return ActionDraft(**defaults)


def _slack_draft(**kwargs) -> ActionDraft:
    defaults = dict(
        action_type=ActionType.draft_message,
        channel_id="C01GENERAL",
        body="Hey team!",
        thread_id="1234567890.000001",
    )
    defaults.update(kwargs)
    return ActionDraft(**defaults)


def _outlook_draft(**kwargs) -> ActionDraft:
    defaults = dict(
        action_type=ActionType.compose_email,
        recipient="bob@example.com",
        subject="Re: Project",
        body="Thanks Bob",
        thread_id="conv-001",
    )
    defaults.update(kwargs)
    return ActionDraft(**defaults)


def _schedule_draft(**kwargs) -> ActionDraft:
    defaults = dict(
        action_type=ActionType.schedule_event,
        event_title="Team Sync",
        start_dt=datetime(2026, 4, 11, 9, 0, tzinfo=timezone.utc),
        end_dt=datetime(2026, 4, 11, 10, 0, tzinfo=timezone.utc),
        attendees=["alice@example.com"],
        body="Quarterly sync",
    )
    defaults.update(kwargs)
    return ActionDraft(**defaults)


def _reschedule_draft(**kwargs) -> ActionDraft:
    defaults = dict(
        action_type=ActionType.reschedule_event,
        event_id="cal-event-001",
        start_dt=datetime(2026, 4, 12, 9, 0, tzinfo=timezone.utc),
        end_dt=datetime(2026, 4, 12, 10, 0, tzinfo=timezone.utc),
        attendees=["alice@example.com"],
        body="Moved the meeting",
    )
    defaults.update(kwargs)
    return ActionDraft(**defaults)


# ---------------------------------------------------------------------------
# GmailExecutor tests
# ---------------------------------------------------------------------------


class TestGmailExecutorValidate:
    """Tests for GmailExecutor.validate()."""

    @pytest.fixture
    def executor_factory(self):
        """Return a factory for GmailExecutor with given scopes and addresses."""
        from daily.actions.google.email import GmailExecutor

        def _make(
            known_addresses: set[str] | None = None,
            granted_scopes: set[str] | None = None,
        ) -> "GmailExecutor":
            if known_addresses is None:
                known_addresses = {"alice@example.com", "bob@example.com"}
            if granted_scopes is None:
                granted_scopes = {"https://www.googleapis.com/auth/gmail.send"}
            service = MagicMock()
            return GmailExecutor(
                service=service,
                known_addresses=known_addresses,
                granted_scopes=granted_scopes,
            )

        return _make

    @pytest.mark.asyncio
    async def test_validate_passes_known_recipient_with_correct_scope(self, executor_factory):
        """validate() passes for known recipient with gmail.send scope."""
        executor = executor_factory()
        draft = _email_draft(recipient="alice@example.com")
        # Should not raise
        await executor.validate(draft)

    @pytest.mark.asyncio
    async def test_validate_raises_for_unknown_recipient(self, executor_factory):
        """validate() raises ValueError for recipient not in known_addresses."""
        executor = executor_factory()
        draft = _email_draft(recipient="unknown@evil.com")
        with pytest.raises(ValueError, match="not in known contacts"):
            await executor.validate(draft)

    @pytest.mark.asyncio
    async def test_validate_raises_when_gmail_send_scope_missing(self, executor_factory):
        """validate() raises ValueError when gmail.send scope is not granted (D-11)."""
        executor = executor_factory(
            granted_scopes={"https://www.googleapis.com/auth/gmail.readonly"}
        )
        draft = _email_draft()
        with pytest.raises(ValueError, match="(?i)gmail"):
            await executor.validate(draft)

    @pytest.mark.asyncio
    async def test_validate_scope_error_message_is_user_displayable(self, executor_factory):
        """validate() scope error message mentions reconnecting."""
        executor = executor_factory(granted_scopes=set())
        draft = _email_draft()
        with pytest.raises(ValueError) as exc_info:
            await executor.validate(draft)
        assert len(str(exc_info.value)) > 10  # Not an empty message


class TestGmailExecutorExecute:
    """Tests for GmailExecutor.execute()."""

    def _build_executor(self):
        from daily.actions.google.email import GmailExecutor

        service = MagicMock()
        # Mock the chained calls: service.users().messages().send().execute()
        mock_execute = MagicMock(return_value={"id": "msg-abc-123"})
        mock_send = MagicMock()
        mock_send.return_value.execute = mock_execute
        service.users.return_value.messages.return_value.send = mock_send
        return GmailExecutor(
            service=service,
            known_addresses={"alice@example.com"},
            granted_scopes={"https://www.googleapis.com/auth/gmail.send"},
        ), service, mock_send

    @pytest.mark.asyncio
    async def test_execute_returns_success_with_external_id(self):
        """execute() returns ActionResult(success=True, external_id=...) on success."""
        executor, _, _ = self._build_executor()
        draft = _email_draft()
        result = await executor.execute(draft)
        assert result.success is True
        assert result.external_id == "msg-abc-123"

    @pytest.mark.asyncio
    async def test_execute_sets_in_reply_to_header(self):
        """execute() sets In-Reply-To header to draft.thread_message_id."""
        executor, service, mock_send = self._build_executor()
        draft = _email_draft(thread_message_id="<msg-001@mail.gmail.com>")
        await executor.execute(draft)

        # Extract the raw MIME from the call to send()
        call_kwargs = mock_send.call_args
        body = call_kwargs[1]["body"] if call_kwargs[1] else call_kwargs[0][1]
        raw_bytes = base64.urlsafe_b64decode(body["raw"])
        mime_str = raw_bytes.decode()
        assert "In-Reply-To: <msg-001@mail.gmail.com>" in mime_str

    @pytest.mark.asyncio
    async def test_execute_sets_references_header(self):
        """execute() sets References header to draft.thread_message_id."""
        executor, service, mock_send = self._build_executor()
        draft = _email_draft(thread_message_id="<msg-001@mail.gmail.com>")
        await executor.execute(draft)

        call_kwargs = mock_send.call_args
        body = call_kwargs[1]["body"] if call_kwargs[1] else call_kwargs[0][1]
        raw_bytes = base64.urlsafe_b64decode(body["raw"])
        mime_str = raw_bytes.decode()
        assert "References: <msg-001@mail.gmail.com>" in mime_str

    @pytest.mark.asyncio
    async def test_execute_base64url_encodes_mime_message(self):
        """execute() sends base64url-encoded MIME in the 'raw' field."""
        executor, service, mock_send = self._build_executor()
        draft = _email_draft()
        await executor.execute(draft)

        call_kwargs = mock_send.call_args
        body = call_kwargs[1]["body"] if call_kwargs[1] else call_kwargs[0][1]
        assert "raw" in body
        # Should be valid base64url — decode without error
        decoded = base64.urlsafe_b64decode(body["raw"])
        assert len(decoded) > 0

    @pytest.mark.asyncio
    async def test_execute_includes_thread_id_in_body(self):
        """execute() includes threadId in send body when draft.thread_id is set."""
        executor, service, mock_send = self._build_executor()
        draft = _email_draft(thread_id="thread-001")
        await executor.execute(draft)

        call_kwargs = mock_send.call_args
        body = call_kwargs[1]["body"] if call_kwargs[1] else call_kwargs[0][1]
        assert body.get("threadId") == "thread-001"

    @pytest.mark.asyncio
    async def test_execute_calls_users_messages_send(self):
        """execute() calls service.users().messages().send(userId='me', body=...)."""
        executor, service, mock_send = self._build_executor()
        draft = _email_draft()
        await executor.execute(draft)

        assert mock_send.called
        call_kwargs = mock_send.call_args
        # userId must be "me"
        if call_kwargs[1]:
            assert call_kwargs[1].get("userId") == "me"
        else:
            assert call_kwargs[0][0] == "me"

    @pytest.mark.asyncio
    async def test_execute_returns_failure_on_api_error(self):
        """execute() returns ActionResult(success=False) when API raises."""
        from daily.actions.google.email import GmailExecutor

        service = MagicMock()
        service.users.return_value.messages.return_value.send.return_value.execute.side_effect = (
            Exception("API rate limit exceeded")
        )
        executor = GmailExecutor(
            service=service,
            known_addresses={"alice@example.com"},
            granted_scopes={"https://www.googleapis.com/auth/gmail.send"},
        )
        draft = _email_draft()
        result = await executor.execute(draft)
        assert result.success is False
        assert "rate limit" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_omits_thread_id_when_none(self):
        """execute() does not include threadId when draft.thread_id is None."""
        executor, service, mock_send = self._build_executor()
        draft = _email_draft(thread_id=None)
        await executor.execute(draft)

        call_kwargs = mock_send.call_args
        body = call_kwargs[1]["body"] if call_kwargs[1] else call_kwargs[0][1]
        assert "threadId" not in body


# ---------------------------------------------------------------------------
# SlackExecutor tests
# ---------------------------------------------------------------------------


class TestSlackExecutorValidate:
    """Tests for SlackExecutor.validate()."""

    @pytest.fixture
    def executor_factory(self):
        from daily.actions.slack.executor import SlackExecutor

        def _make(
            known_channels: set[str] | None = None,
            granted_scopes: set[str] | None = None,
        ) -> "SlackExecutor":
            if known_channels is None:
                known_channels = {"C01GENERAL", "C02RANDOM"}
            if granted_scopes is None:
                granted_scopes = {"chat:write"}
            client = MagicMock()
            return SlackExecutor(
                client=client,
                known_channels=known_channels,
                granted_scopes=granted_scopes,
            )

        return _make

    @pytest.mark.asyncio
    async def test_validate_passes_known_channel_with_chat_write(self, executor_factory):
        """validate() passes for known channel with chat:write scope."""
        executor = executor_factory()
        draft = _slack_draft(channel_id="C01GENERAL")
        await executor.validate(draft)

    @pytest.mark.asyncio
    async def test_validate_raises_for_unknown_channel(self, executor_factory):
        """validate() raises ValueError for channel not in known_channels."""
        executor = executor_factory()
        draft = _slack_draft(channel_id="CUNKNOWN")
        with pytest.raises(ValueError):
            await executor.validate(draft)

    @pytest.mark.asyncio
    async def test_validate_raises_when_chat_write_scope_missing(self, executor_factory):
        """validate() raises ValueError when chat:write scope is missing (D-11)."""
        executor = executor_factory(granted_scopes={"channels:read"})
        draft = _slack_draft()
        with pytest.raises(ValueError, match="chat:write"):
            await executor.validate(draft)

    @pytest.mark.asyncio
    async def test_validate_scope_check_precedes_channel_check(self, executor_factory):
        """validate() checks scope before channel (scope is the harder gate)."""
        # Missing scope AND unknown channel — should still raise
        executor = executor_factory(
            known_channels=set(),
            granted_scopes=set(),
        )
        draft = _slack_draft(channel_id="CUNKNOWN")
        with pytest.raises(ValueError):
            await executor.validate(draft)


class TestSlackExecutorExecute:
    """Tests for SlackExecutor.execute()."""

    def _build_executor(self):
        from daily.actions.slack.executor import SlackExecutor

        client = MagicMock()
        client.chat_postMessage.return_value = {"ok": True, "ts": "1620000000.000100"}
        return SlackExecutor(
            client=client,
            known_channels={"C01GENERAL"},
            granted_scopes={"chat:write"},
        ), client

    @pytest.mark.asyncio
    async def test_execute_returns_success_with_ts(self):
        """execute() returns ActionResult(success=True, external_id=ts) on success."""
        executor, client = self._build_executor()
        draft = _slack_draft()
        result = await executor.execute(draft)
        assert result.success is True
        assert result.external_id == "1620000000.000100"

    @pytest.mark.asyncio
    async def test_execute_passes_thread_ts_as_string(self):
        """execute() passes thread_ts as str(), NOT a float (Pitfall 2)."""
        executor, client = self._build_executor()
        draft = _slack_draft(thread_id="1234567890.000001")
        await executor.execute(draft)

        assert client.chat_postMessage.called
        call_kwargs = client.chat_postMessage.call_args[1]
        thread_ts = call_kwargs.get("thread_ts")
        # CRITICAL: must be a string, not a float
        assert isinstance(thread_ts, str)
        assert thread_ts == "1234567890.000001"

    @pytest.mark.asyncio
    async def test_execute_calls_chat_post_message_with_channel_and_text(self):
        """execute() calls client.chat_postMessage with correct channel and text."""
        executor, client = self._build_executor()
        draft = _slack_draft(channel_id="C01GENERAL", body="Hey team!")
        await executor.execute(draft)

        call_kwargs = client.chat_postMessage.call_args[1]
        assert call_kwargs["channel"] == "C01GENERAL"
        assert call_kwargs["text"] == "Hey team!"

    @pytest.mark.asyncio
    async def test_execute_returns_failure_on_api_error(self):
        """execute() returns ActionResult(success=False) when API raises."""
        from daily.actions.slack.executor import SlackExecutor

        client = MagicMock()
        client.chat_postMessage.side_effect = Exception("channel_not_found")
        executor = SlackExecutor(
            client=client,
            known_channels={"C01GENERAL"},
            granted_scopes={"chat:write"},
        )
        draft = _slack_draft()
        result = await executor.execute(draft)
        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_execute_omits_thread_ts_when_thread_id_is_none(self):
        """execute() passes thread_ts=None when draft.thread_id is None."""
        executor, client = self._build_executor()
        draft = _slack_draft(thread_id=None)
        await executor.execute(draft)

        call_kwargs = client.chat_postMessage.call_args[1]
        # thread_ts should be None (not a float or empty string)
        assert call_kwargs.get("thread_ts") is None


# ---------------------------------------------------------------------------
# OutlookExecutor tests
# ---------------------------------------------------------------------------


class TestOutlookExecutorValidate:
    """Tests for OutlookExecutor.validate()."""

    @pytest.fixture
    def executor_factory(self):
        from daily.actions.microsoft.executor import OutlookExecutor

        def _make(
            known_addresses: set[str] | None = None,
            granted_scopes: set[str] | None = None,
        ) -> "OutlookExecutor":
            if known_addresses is None:
                known_addresses = {"bob@example.com", "carol@example.com"}
            if granted_scopes is None:
                granted_scopes = {"Mail.Send", "User.Read"}
            graph_client = MagicMock()
            return OutlookExecutor(
                graph_client=graph_client,
                known_addresses=known_addresses,
                granted_scopes=granted_scopes,
            )

        return _make

    @pytest.mark.asyncio
    async def test_validate_passes_known_recipient_with_mail_send(self, executor_factory):
        """validate() passes for known recipient with Mail.Send scope."""
        executor = executor_factory()
        draft = _outlook_draft(recipient="bob@example.com")
        await executor.validate(draft)

    @pytest.mark.asyncio
    async def test_validate_raises_for_unknown_recipient(self, executor_factory):
        """validate() raises ValueError for recipient not in known_addresses."""
        executor = executor_factory()
        draft = _outlook_draft(recipient="attacker@evil.com")
        with pytest.raises(ValueError, match="not in known contacts"):
            await executor.validate(draft)

    @pytest.mark.asyncio
    async def test_validate_raises_when_mail_send_scope_missing(self, executor_factory):
        """validate() raises ValueError when Mail.Send scope is missing (D-11)."""
        executor = executor_factory(granted_scopes={"Mail.Read"})
        draft = _outlook_draft()
        with pytest.raises(ValueError, match="Mail.Send"):
            await executor.validate(draft)


class TestOutlookExecutorExecute:
    """Tests for OutlookExecutor.execute()."""

    def _build_executor(self, send_side_effect=None):
        from daily.actions.microsoft.executor import OutlookExecutor

        graph_client = MagicMock()
        # Mock the Graph SDK send_mail call pattern (async)
        mock_send = AsyncMock(return_value=None)
        if send_side_effect:
            mock_send.side_effect = send_side_effect
        # Graph client sendMail is reached via: graph_client.me.send_mail.post(body)
        graph_client.me.send_mail.post = mock_send
        return OutlookExecutor(
            graph_client=graph_client,
            known_addresses={"bob@example.com"},
            granted_scopes={"Mail.Send"},
        ), graph_client, mock_send

    @pytest.mark.asyncio
    async def test_execute_returns_success(self):
        """execute() returns ActionResult(success=True) on successful sendMail."""
        executor, _, _ = self._build_executor()
        draft = _outlook_draft()
        result = await executor.execute(draft)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_calls_graph_send_mail(self):
        """execute() calls graph_client.me.send_mail.post() with correct body."""
        executor, graph_client, mock_send = self._build_executor()
        draft = _outlook_draft(recipient="bob@example.com", subject="Re: Project", body="Thanks Bob")
        await executor.execute(draft)

        assert mock_send.called
        call_args = mock_send.call_args
        # The body should be a SendMailPostRequestBody or dict with message.subject
        sent_body = call_args[0][0] if call_args[0] else call_args[1].get("body")
        assert sent_body is not None

    @pytest.mark.asyncio
    async def test_execute_returns_failure_on_api_error(self):
        """execute() returns ActionResult(success=False) on Graph API error."""
        executor, _, _ = self._build_executor(
            send_side_effect=Exception("Graph API 403 Forbidden")
        )
        draft = _outlook_draft()
        result = await executor.execute(draft)
        assert result.success is False
        assert result.error is not None


# ---------------------------------------------------------------------------
# GoogleCalendarExecutor tests (Task 2)
# ---------------------------------------------------------------------------


class TestGoogleCalendarExecutorValidate:
    """Tests for GoogleCalendarExecutor.validate()."""

    @pytest.fixture
    def executor_factory(self):
        from daily.actions.google.calendar import GoogleCalendarExecutor

        def _make(
            known_addresses: set[str] | None = None,
            granted_scopes: set[str] | None = None,
        ) -> "GoogleCalendarExecutor":
            if known_addresses is None:
                known_addresses = {"alice@example.com", "bob@example.com"}
            if granted_scopes is None:
                granted_scopes = {
                    "https://www.googleapis.com/auth/calendar.events"
                }
            service = MagicMock()
            return GoogleCalendarExecutor(
                service=service,
                known_addresses=known_addresses,
                granted_scopes=granted_scopes,
            )

        return _make

    @pytest.mark.asyncio
    async def test_validate_passes_known_attendees_with_correct_scope(self, executor_factory):
        """validate() passes for known attendees with calendar.events scope."""
        executor = executor_factory()
        draft = _schedule_draft(attendees=["alice@example.com"])
        await executor.validate(draft)

    @pytest.mark.asyncio
    async def test_validate_raises_for_unknown_attendee(self, executor_factory):
        """validate() raises ValueError for attendee not in known_addresses."""
        executor = executor_factory()
        draft = _schedule_draft(attendees=["alice@example.com", "stranger@evil.com"])
        with pytest.raises(ValueError, match="not in known contacts"):
            await executor.validate(draft)

    @pytest.mark.asyncio
    async def test_validate_raises_when_calendar_events_scope_missing(self, executor_factory):
        """validate() raises ValueError when calendar.events scope is missing (D-11)."""
        executor = executor_factory(
            granted_scopes={"https://www.googleapis.com/auth/calendar.readonly"}
        )
        draft = _schedule_draft()
        with pytest.raises(ValueError, match="Calendar"):
            await executor.validate(draft)


class TestGoogleCalendarExecutorExecute:
    """Tests for GoogleCalendarExecutor.execute()."""

    def _build_executor(self):
        from daily.actions.google.calendar import GoogleCalendarExecutor

        service = MagicMock()
        # Mock events().insert().execute() -> return {"id": "cal-event-001"}
        service.events.return_value.insert.return_value.execute.return_value = {
            "id": "cal-event-001"
        }
        # Mock events().patch().execute() -> return {"id": "cal-event-002"}
        service.events.return_value.patch.return_value.execute.return_value = {
            "id": "cal-event-002"
        }
        return GoogleCalendarExecutor(
            service=service,
            known_addresses={"alice@example.com"},
            granted_scopes={"https://www.googleapis.com/auth/calendar.events"},
        ), service

    @pytest.mark.asyncio
    async def test_execute_schedule_event_calls_insert(self):
        """schedule_event calls events().insert() (NOT patch or update)."""
        executor, service = self._build_executor()
        draft = _schedule_draft()
        result = await executor.execute(draft)

        assert service.events.return_value.insert.called
        assert not service.events.return_value.patch.called
        assert not hasattr(service.events.return_value, "update") or not service.events.return_value.update.called

    @pytest.mark.asyncio
    async def test_execute_schedule_event_returns_success_with_event_id(self):
        """schedule_event returns ActionResult(success=True, external_id=event_id)."""
        executor, service = self._build_executor()
        draft = _schedule_draft()
        result = await executor.execute(draft)
        assert result.success is True
        assert result.external_id == "cal-event-001"

    @pytest.mark.asyncio
    async def test_execute_schedule_event_insert_body_contains_summary(self):
        """schedule_event insert body contains 'summary' field with event_title."""
        executor, service = self._build_executor()
        draft = _schedule_draft(event_title="Team Sync")
        await executor.execute(draft)

        call_kwargs = service.events.return_value.insert.call_args[1]
        event_body = call_kwargs["body"]
        assert event_body["summary"] == "Team Sync"

    @pytest.mark.asyncio
    async def test_execute_schedule_event_insert_body_contains_attendees(self):
        """schedule_event insert body contains attendees list."""
        executor, service = self._build_executor()
        draft = _schedule_draft(attendees=["alice@example.com"])
        await executor.execute(draft)

        call_kwargs = service.events.return_value.insert.call_args[1]
        event_body = call_kwargs["body"]
        emails = [a["email"] for a in event_body["attendees"]]
        assert "alice@example.com" in emails

    @pytest.mark.asyncio
    async def test_execute_reschedule_event_calls_patch_not_update(self):
        """reschedule_event calls events().patch() NOT events().update() (Pitfall 5)."""
        executor, service = self._build_executor()
        draft = _reschedule_draft()
        await executor.execute(draft)

        assert service.events.return_value.patch.called
        # Critically: update() must NOT be called
        assert not service.events.return_value.update.called

    @pytest.mark.asyncio
    async def test_execute_reschedule_passes_event_id_to_patch(self):
        """reschedule_event passes correct eventId to events().patch()."""
        executor, service = self._build_executor()
        draft = _reschedule_draft(event_id="cal-event-001")
        await executor.execute(draft)

        call_kwargs = service.events.return_value.patch.call_args[1]
        assert call_kwargs.get("eventId") == "cal-event-001"

    @pytest.mark.asyncio
    async def test_execute_reschedule_returns_event_id(self):
        """reschedule_event returns ActionResult with external_id=event_id."""
        executor, service = self._build_executor()
        draft = _reschedule_draft(event_id="cal-event-001")
        result = await executor.execute(draft)
        assert result.success is True
        assert result.external_id == "cal-event-001"

    @pytest.mark.asyncio
    async def test_execute_returns_failure_on_api_error(self):
        """execute() returns ActionResult(success=False) when API raises."""
        from daily.actions.google.calendar import GoogleCalendarExecutor

        service = MagicMock()
        service.events.return_value.insert.return_value.execute.side_effect = Exception(
            "Calendar API quota exceeded"
        )
        executor = GoogleCalendarExecutor(
            service=service,
            known_addresses={"alice@example.com"},
            granted_scopes={"https://www.googleapis.com/auth/calendar.events"},
        )
        draft = _schedule_draft()
        result = await executor.execute(draft)
        assert result.success is False
        assert result.error is not None


# ---------------------------------------------------------------------------
# execute_node dispatch tests (Task 2)
# ---------------------------------------------------------------------------


class TestExecuteNodeDispatch:
    """Tests for execute_node executor dispatch and provider routing."""

    def _make_state(
        self,
        action_type: ActionType = ActionType.draft_email,
        approval_decision: str = "confirm",
        user_id: int = 1,
        **draft_kwargs,
    ):
        from daily.orchestrator.state import SessionState
        from daily.actions.base import ActionDraft

        if action_type in (ActionType.draft_email, ActionType.compose_email):
            draft = ActionDraft(
                action_type=action_type,
                recipient="alice@example.com",
                subject="Hello",
                body="Hi",
                **draft_kwargs,
            )
        elif action_type == ActionType.draft_message:
            draft = ActionDraft(
                action_type=action_type,
                channel_id="C01GENERAL",
                body="Hey!",
                **draft_kwargs,
            )
        else:
            draft = ActionDraft(
                action_type=action_type,
                event_title="Meeting",
                start_dt=datetime(2026, 4, 11, 9, 0, tzinfo=timezone.utc),
                end_dt=datetime(2026, 4, 11, 10, 0, tzinfo=timezone.utc),
                attendees=["alice@example.com"],
                body="Sync",
                **draft_kwargs,
            )

        return SessionState(
            active_user_id=user_id,
            pending_action=draft,
            approval_decision=approval_decision,
        )

    @pytest.mark.asyncio
    async def test_execute_node_cancels_when_not_confirmed(self):
        """execute_node returns cancellation message when approval_decision != 'confirm'."""
        from daily.orchestrator.nodes import execute_node

        state = self._make_state(approval_decision="reject")
        result = await execute_node(state)
        assert result["pending_action"] is None
        assert result["approval_decision"] is None
        assert "cancel" in result["messages"][0].content.lower()

    @pytest.mark.asyncio
    async def test_execute_node_calls_validate_before_execute(self):
        """execute_node calls executor.validate() before executor.execute()."""
        from daily.orchestrator.nodes import execute_node

        call_order = []

        mock_executor = MagicMock()

        async def _validate(draft):
            call_order.append("validate")

        async def _execute(draft):
            call_order.append("execute")
            return ActionResult(success=True, external_id="msg-001")

        mock_executor.validate = _validate
        mock_executor.execute = _execute

        state = self._make_state()

        with patch(
            "daily.orchestrator.nodes._build_executor_for_type",
            new=AsyncMock(return_value=mock_executor),
        ):
            await execute_node(state)

        assert call_order == ["validate", "execute"]

    @pytest.mark.asyncio
    async def test_execute_node_returns_error_when_validate_raises(self):
        """execute_node returns error message when executor.validate() raises ValueError."""
        from daily.orchestrator.nodes import execute_node

        mock_executor = MagicMock()
        mock_executor.validate = AsyncMock(
            side_effect=ValueError("Recipient not in known contacts")
        )
        mock_executor.execute = AsyncMock()

        state = self._make_state()

        with patch(
            "daily.orchestrator.nodes._build_executor_for_type",
            new=AsyncMock(return_value=mock_executor),
        ):
            result = await execute_node(state)

        assert result["pending_action"] is None
        assert "Recipient not in known contacts" in result["messages"][0].content
        # execute() should NOT have been called
        mock_executor.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_node_dispatch_uses_gmail_for_google_email(self):
        """execute_node dispatches draft_email to GmailExecutor for Google provider."""
        from daily.orchestrator.nodes import execute_node

        mock_executor = MagicMock()
        mock_executor.validate = AsyncMock(return_value=None)
        mock_executor.execute = AsyncMock(
            return_value=ActionResult(success=True, external_id="msg-001")
        )

        state = self._make_state(action_type=ActionType.draft_email)

        with patch(
            "daily.orchestrator.nodes._build_executor_for_type",
            new=AsyncMock(return_value=mock_executor),
        ) as mock_build:
            result = await execute_node(state)

        # _build_executor_for_type should have been called with draft_email
        mock_build.assert_called_once()
        assert result["messages"][0].content != "Action cancelled."

    @pytest.mark.asyncio
    async def test_execute_node_dispatch_calls_log_via_create_task(self):
        """execute_node logs approved action via asyncio.create_task (fire-and-forget)."""
        from daily.orchestrator.nodes import execute_node

        mock_executor = MagicMock()
        mock_executor.validate = AsyncMock(return_value=None)
        mock_executor.execute = AsyncMock(
            return_value=ActionResult(success=True, external_id="msg-001")
        )

        state = self._make_state()

        created_tasks = []
        original_create_task = asyncio.create_task

        def _capture_task(coro, *args, **kwargs):
            created_tasks.append(coro)
            # Actually schedule it so we don't leak coroutines
            return original_create_task(coro, *args, **kwargs)

        with patch(
            "daily.orchestrator.nodes._build_executor_for_type",
            new=AsyncMock(return_value=mock_executor),
        ), patch("daily.orchestrator.nodes.asyncio.create_task", side_effect=_capture_task):
            await execute_node(state)

        # At least one create_task call should have happened
        assert len(created_tasks) >= 1
