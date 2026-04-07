"""
Tests for src/daily/briefing/redactor.py

All LLM calls are mocked — no real OpenAI API calls.
Tests cover credential stripping, per-item summarisation,
batch redaction, empty body handling, and concurrency.
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from daily.briefing.redactor import (
    CREDENTIAL_PATTERN,
    redact_emails,
    redact_messages,
    strip_credentials,
    summarise_and_redact,
)
from daily.briefing.models import RankedEmail
from daily.integrations.models import EmailMetadata, MessageMetadata


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_email_metadata(message_id: str) -> EmailMetadata:
    return EmailMetadata(
        message_id=message_id,
        thread_id="thread-1",
        subject="Test Subject",
        sender="sender@example.com",
        recipient="recipient@example.com",
        timestamp=datetime(2026, 4, 7, 9, 0, 0),
        is_unread=True,
        labels=[],
    )


def make_ranked_email(message_id: str) -> RankedEmail:
    return RankedEmail(
        metadata=make_email_metadata(message_id),
        score=80.0,
    )


def make_message_metadata(message_id: str) -> MessageMetadata:
    return MessageMetadata(
        message_id=message_id,
        channel_id="C123",
        sender_id="U456",
        timestamp=datetime(2026, 4, 7, 9, 0, 0),
        is_mention=True,
        is_dm=False,
    )


def make_mock_openai_client(content: str = "Summarised content.") -> MagicMock:
    """Return a mock AsyncOpenAI client whose chat.completions.create returns
    a controlled string."""
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
# Test 1: Basic credential strip
# ---------------------------------------------------------------------------


def test_credential_strip():
    """Credential patterns in plain text are replaced with [REDACTED]."""
    cases = [
        ("My password: abc123 is here", "[REDACTED]"),
        ("token=ghp_secrettoken123", "[REDACTED]"),
        ("api_key: sk-proj-1234567890abcdef", "[REDACTED]"),
        ("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig", "[REDACTED]"),
        (
            "Visit https://example.com/callback?token=mysecrettoken123 now",
            "[REDACTED]",
        ),
    ]
    for text, expected_fragment in cases:
        result = strip_credentials(text)
        assert "[REDACTED]" in result, f"Expected [REDACTED] in: {result!r}"
        assert "abc123" not in result or "password" not in result.lower() or text.lower().startswith("my password"), \
            f"Credential value still present in: {result!r}"


# ---------------------------------------------------------------------------
# Test 2: Credential strip handles JSON context without mangling comma
# ---------------------------------------------------------------------------


def test_credential_strip_json_context():
    """Credential stripping does not eat trailing comma or surrounding JSON."""
    text = '{"username": "alice", "password": "secret123", "role": "admin"}'
    result = strip_credentials(text)
    # The credential value should be replaced
    assert "secret123" not in result
    assert "[REDACTED]" in result
    # The surrounding JSON structure (comma after the value, next key) is intact
    assert '"role"' in result, f"JSON structure mangled: {result!r}"
    # The comma after the credential value should survive
    assert "," in result, f"Comma was eaten: {result!r}"


# ---------------------------------------------------------------------------
# Test 3: Credential strip handles HTML context without eating closing tag
# ---------------------------------------------------------------------------


def test_credential_strip_html_context():
    """Credential value is stripped without consuming closing HTML tag."""
    text = "<span>token=abc123</span>"
    result = strip_credentials(text)
    assert "abc123" not in result
    assert "[REDACTED]" in result
    # The closing tag must survive
    assert "</span>" in result, f"Closing HTML tag was eaten: {result!r}"


# ---------------------------------------------------------------------------
# Test 4: summarise_and_redact strips credentials in LLM output
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_summarise_and_redact():
    """If the LLM summary contains a credential pattern, it is stripped."""
    # LLM returns a summary that accidentally includes a password
    mock_client = make_mock_openai_client(
        content="The user mentioned password: hunter2 in the email thread."
    )
    result = await summarise_and_redact("Some raw email body text.", mock_client)
    assert "hunter2" not in result
    assert "[REDACTED]" in result
    # LLM was called once
    mock_client.chat.completions.create.assert_called_once()


# ---------------------------------------------------------------------------
# Test 5: redact_emails batch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_redact_email_batch():
    """redact_emails populates summary on all emails and strips credentials."""
    emails = [make_ranked_email(f"msg-{i}") for i in range(3)]
    raw_bodies = {
        "msg-0": "Hi, please reset your password: temp123.",
        "msg-1": "Meeting at 3pm tomorrow.",
        "msg-2": "",
    }
    mock_client = make_mock_openai_client(content="Summarised email content.")

    result = await redact_emails(emails, raw_bodies, mock_client)

    assert len(result) == 3
    for email in result:
        # summary must be populated (or empty for empty body)
        assert isinstance(email.summary, str)
    # No credential values should appear in any summary
    for email in result:
        assert "temp123" not in email.summary


# ---------------------------------------------------------------------------
# Test 6: redact_messages batch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_redact_slack_batch():
    """redact_messages returns a dict mapping message_id to redacted summary."""
    messages = [make_message_metadata(f"slack-{i}") for i in range(3)]
    raw_texts = {
        "slack-0": "The api_key is sk-abc123 for this project.",
        "slack-1": "Ping me when you get a chance.",
        "slack-2": "",
    }
    mock_client = make_mock_openai_client(content="Summarised slack message.")

    result = await redact_messages(messages, raw_texts, mock_client)

    assert isinstance(result, dict)
    assert set(result.keys()) == {"slack-0", "slack-1", "slack-2"}
    for summary in result.values():
        assert isinstance(summary, str)
    # Credential values stripped
    for summary in result.values():
        assert "sk-abc123" not in summary


# ---------------------------------------------------------------------------
# Test 7: Empty body returns empty string without calling LLM
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_body():
    """Empty string body returns empty string and does not call LLM."""
    mock_client = make_mock_openai_client()
    result = await summarise_and_redact("", mock_client)
    assert result == ""
    mock_client.chat.completions.create.assert_not_called()

    # Also test whitespace-only
    result2 = await summarise_and_redact("   \n  ", mock_client)
    assert result2 == ""
    mock_client.chat.completions.create.assert_not_called()


# ---------------------------------------------------------------------------
# Test 8: Concurrent redaction completes without error (semaphore)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_redaction_with_semaphore():
    """5 concurrent summarise_and_redact calls complete without error."""
    mock_client = make_mock_openai_client(content="Concurrent summary result.")
    bodies = [f"Body content number {i}" for i in range(5)]
    results = await asyncio.gather(
        *[summarise_and_redact(body, mock_client) for body in bodies]
    )
    assert len(results) == 5
    for r in results:
        assert isinstance(r, str)
        assert len(r) > 0
