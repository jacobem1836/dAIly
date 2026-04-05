"""
Tests for integration adapter Pydantic models and abstract base classes.

Validates:
- Model field presence and correct types
- Privacy constraint: no body/raw_body/content/text fields in any model (SEC-04/D-06)
- Abstract adapter classes enforce the D-08 interface contract
"""

import inspect
from datetime import datetime

import pytest


# --- Model field presence tests ---


def test_email_metadata_has_required_fields():
    from daily.integrations.models import EmailMetadata

    fields = EmailMetadata.model_fields
    assert "message_id" in fields
    assert "thread_id" in fields
    assert "subject" in fields
    assert "sender" in fields
    assert "recipient" in fields
    assert "timestamp" in fields
    assert "is_unread" in fields
    assert "labels" in fields


def test_email_metadata_has_no_body_fields():
    """SEC-04: no body/raw_body/content/text/message_body field allowed."""
    from daily.integrations.models import EmailMetadata

    forbidden = {"body", "raw_body", "content", "text", "message_body"}
    fields = set(EmailMetadata.model_fields.keys())
    overlap = forbidden & fields
    assert overlap == set(), f"EmailMetadata has forbidden fields: {overlap}"


def test_message_metadata_has_no_body_fields():
    """SEC-04: no body/raw_body/content/text/message_body field allowed."""
    from daily.integrations.models import MessageMetadata

    forbidden = {"body", "raw_body", "content", "text", "message_body"}
    fields = set(MessageMetadata.model_fields.keys())
    overlap = forbidden & fields
    assert overlap == set(), f"MessageMetadata has forbidden fields: {overlap}"


def test_calendar_event_has_no_body_fields():
    """SEC-04: no body/raw_body/content field allowed in CalendarEvent."""
    from daily.integrations.models import CalendarEvent

    forbidden = {"body", "raw_body", "content"}
    fields = set(CalendarEvent.model_fields.keys())
    overlap = forbidden & fields
    assert overlap == set(), f"CalendarEvent has forbidden fields: {overlap}"


def test_email_page_has_required_fields():
    from daily.integrations.models import EmailPage

    fields = EmailPage.model_fields
    assert "emails" in fields
    assert "next_page_token" in fields


def test_message_page_has_required_fields():
    from daily.integrations.models import MessagePage

    fields = MessagePage.model_fields
    assert "messages" in fields
    assert "next_cursor" in fields


def test_calendar_event_has_required_fields():
    from daily.integrations.models import CalendarEvent

    fields = CalendarEvent.model_fields
    assert "event_id" in fields
    assert "title" in fields
    assert "start" in fields
    assert "end" in fields
    assert "attendees" in fields
    assert "location" in fields
    assert "is_all_day" in fields


# --- Abstract adapter interface tests ---


def test_email_adapter_has_list_emails_method():
    from daily.integrations.base import EmailAdapter

    assert hasattr(EmailAdapter, "list_emails")
    method = getattr(EmailAdapter, "list_emails")
    sig = inspect.signature(method)
    params = list(sig.parameters.keys())
    assert "self" in params
    assert "since" in params
    assert "page_token" in params


def test_calendar_adapter_has_list_events_method():
    from daily.integrations.base import CalendarAdapter

    assert hasattr(CalendarAdapter, "list_events")
    method = getattr(CalendarAdapter, "list_events")
    sig = inspect.signature(method)
    params = list(sig.parameters.keys())
    assert "self" in params
    assert "since" in params
    assert "until" in params


def test_message_adapter_has_list_messages_method():
    from daily.integrations.base import MessageAdapter

    assert hasattr(MessageAdapter, "list_messages")
    method = getattr(MessageAdapter, "list_messages")
    sig = inspect.signature(method)
    params = list(sig.parameters.keys())
    assert "self" in params
    assert "channels" in params
    assert "since" in params


def test_email_adapter_is_abstract():
    """Cannot instantiate EmailAdapter without implementing list_emails."""
    from daily.integrations.base import EmailAdapter

    with pytest.raises(TypeError):
        EmailAdapter()  # type: ignore


def test_calendar_adapter_is_abstract():
    """Cannot instantiate CalendarAdapter without implementing list_events."""
    from daily.integrations.base import CalendarAdapter

    with pytest.raises(TypeError):
        CalendarAdapter()  # type: ignore


def test_message_adapter_is_abstract():
    """Cannot instantiate MessageAdapter without implementing list_messages."""
    from daily.integrations.base import MessageAdapter

    with pytest.raises(TypeError):
        MessageAdapter()  # type: ignore


# --- Model instantiation smoke tests ---


def test_email_metadata_instantiation():
    from daily.integrations.models import EmailMetadata

    m = EmailMetadata(
        message_id="msg1",
        thread_id="thread1",
        subject="Hello",
        sender="a@example.com",
        recipient="b@example.com",
        timestamp=datetime(2026, 4, 5, 8, 0, 0),
        is_unread=True,
        labels=["INBOX"],
    )
    assert m.message_id == "msg1"
    assert m.labels == ["INBOX"]


def test_email_page_instantiation():
    from daily.integrations.models import EmailMetadata, EmailPage

    emails = [
        EmailMetadata(
            message_id="m1",
            thread_id="t1",
            subject="Test",
            sender="a@b.com",
            recipient="c@d.com",
            timestamp=datetime(2026, 4, 5),
            is_unread=False,
            labels=[],
        )
    ]
    page = EmailPage(emails=emails, next_page_token=None)
    assert len(page.emails) == 1
    assert page.next_page_token is None


def test_calendar_event_instantiation():
    from daily.integrations.models import CalendarEvent

    ev = CalendarEvent(
        event_id="ev1",
        title="Standup",
        start=datetime(2026, 4, 5, 9, 0),
        end=datetime(2026, 4, 5, 9, 30),
        attendees=["a@b.com"],
        location=None,
        is_all_day=False,
    )
    assert ev.title == "Standup"
    assert ev.location is None


def test_message_page_instantiation():
    from daily.integrations.models import MessageMetadata, MessagePage

    msgs = [
        MessageMetadata(
            message_id="m1",
            channel_id="C001",
            sender_id="U001",
            timestamp=datetime(2026, 4, 5, 10, 0),
            is_mention=False,
            is_dm=True,
        )
    ]
    page = MessagePage(messages=msgs, next_cursor=None)
    assert len(page.messages) == 1
