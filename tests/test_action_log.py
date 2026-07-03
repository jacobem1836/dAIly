"""Tests for append_action_log() service function.

Tests:
- SHA-256 body_hash matches hashlib output
- full_body is never persisted onto the row (audit M-1: no content_summary
  or any other plaintext/truncated body field is stored — only body_hash)
"""
import hashlib
from unittest.mock import AsyncMock

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
        full_body=body,
        approval_status="approved",
        outcome="sent",
        session=session,
    )

    row = session.add.call_args[0][0]
    assert row.body_hash == expected
    assert len(row.body_hash) == 64  # SHA-256 hex = 64 chars


@pytest.mark.asyncio
async def test_append_action_log_never_persists_raw_body_or_summary():
    """append_action_log's ActionLog row has no attribute holding the raw body text.

    Audit M-1 regression guard: previously content_summary stored the first
    200 chars of the raw body in plaintext. Assert the persisted row has no
    column value equal to (or containing) the full body text.
    """
    from daily.actions.log import append_action_log
    from daily.actions.models import ActionLog

    session = AsyncMock(spec=AsyncSession)
    full_body = "Secret meeting notes: the acquisition closes Friday."

    await append_action_log(
        user_id=1,
        action_type="draft_email",
        target="alice@example.com",
        full_body=full_body,
        approval_status="approved",
        outcome=None,
        session=session,
    )

    row = session.add.call_args[0][0]
    assert not hasattr(row, "content_summary")
    for column in ActionLog.__table__.columns:
        value = getattr(row, column.key, None)
        if isinstance(value, str):
            assert full_body not in value


@pytest.mark.asyncio
async def test_append_action_log_commits_session():
    """append_action_log calls session.commit()."""
    from daily.actions.log import append_action_log

    session = AsyncMock(spec=AsyncSession)

    await append_action_log(
        user_id=1,
        action_type="draft_email",
        target="test@example.com",
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
