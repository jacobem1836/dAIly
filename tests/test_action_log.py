"""Tests for append_action_log() service function.

TDD RED phase — tests must fail until log.py is implemented.

Tests:
- SHA-256 body_hash matches hashlib output
- content_summary truncated to 200 chars
- Long body stores only first 200 chars in content_summary
"""
import hashlib
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_body_hash_is_sha256_of_full_body():
    """append_action_log stores SHA-256 hex digest of full_body in body_hash."""
    from daily.actions.log import append_action_log
    from daily.actions.models import ActionLog

    session = AsyncMock(spec=AsyncSession)
    full_body = "Hello Bob, thank you for your time yesterday."
    expected_hash = hashlib.sha256(full_body.encode()).hexdigest()

    await append_action_log(
        user_id=1,
        action_type="draft_email",
        target="bob@example.com",
        content_summary=full_body[:200],
        full_body=full_body,
        approval_status="approved",
        outcome="sent",
        session=session,
    )

    session.add.assert_called_once()
    row = session.add.call_args[0][0]
    assert isinstance(row, ActionLog)
    assert row.body_hash == expected_hash


@pytest.mark.asyncio
async def test_content_summary_truncated_to_200_chars():
    """append_action_log truncates content_summary to 200 chars."""
    from daily.actions.log import append_action_log
    from daily.actions.models import ActionLog

    session = AsyncMock(spec=AsyncSession)
    long_summary = "A" * 500

    await append_action_log(
        user_id=1,
        action_type="draft_email",
        target="alice@example.com",
        content_summary=long_summary,
        full_body=long_summary,
        approval_status="approved",
        outcome=None,
        session=session,
    )

    row = session.add.call_args[0][0]
    assert len(row.content_summary) == 200
    assert row.content_summary == "A" * 200


@pytest.mark.asyncio
async def test_content_summary_short_body_stored_as_is():
    """append_action_log stores content_summary unchanged when under 200 chars."""
    from daily.actions.log import append_action_log
    from daily.actions.models import ActionLog

    session = AsyncMock(spec=AsyncSession)
    short_body = "Short message"

    await append_action_log(
        user_id=1,
        action_type="draft_message",
        target="C01GENERAL",
        content_summary=short_body,
        full_body=short_body,
        approval_status="rejected",
        outcome=None,
        session=session,
    )

    row = session.add.call_args[0][0]
    assert row.content_summary == short_body


@pytest.mark.asyncio
async def test_body_hash_matches_hashlib_sha256():
    """body_hash matches hashlib.sha256(full_body.encode()).hexdigest()."""
    from daily.actions.log import append_action_log
    from daily.actions.models import ActionLog

    session = AsyncMock(spec=AsyncSession)
    body = "This is a longer draft email body with some PII content."
    expected = hashlib.sha256(body.encode()).hexdigest()

    await append_action_log(
        user_id=42,
        action_type="compose_email",
        target="ceo@example.com",
        content_summary=body[:200],
        full_body=body,
        approval_status="approved",
        outcome="sent",
        session=session,
    )

    row = session.add.call_args[0][0]
    assert row.body_hash == expected
    assert len(row.body_hash) == 64  # SHA-256 hex = 64 chars


@pytest.mark.asyncio
async def test_append_action_log_commits_session():
    """append_action_log calls session.commit()."""
    from daily.actions.log import append_action_log

    session = AsyncMock(spec=AsyncSession)

    await append_action_log(
        user_id=1,
        action_type="draft_email",
        target="test@example.com",
        content_summary="Test",
        full_body="Test body",
        approval_status="pending",
        outcome=None,
        session=session,
    )

    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_action_log_row_stores_correct_fields():
    """append_action_log creates ActionLog row with all expected field values."""
    from daily.actions.log import append_action_log
    from daily.actions.models import ActionLog

    session = AsyncMock(spec=AsyncSession)

    await append_action_log(
        user_id=7,
        action_type="schedule_event",
        target="evt-001",
        content_summary="Team sync",
        full_body="Team sync at 9am",
        approval_status="approved",
        outcome="sent",
        session=session,
    )

    row = session.add.call_args[0][0]
    assert row.user_id == 7
    assert row.action_type == "schedule_event"
    assert row.target == "evt-001"
    assert row.approval_status == "approved"
    assert row.outcome == "sent"
