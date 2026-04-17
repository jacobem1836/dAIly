"""Tests for the heuristic email ranker (Plan 02-02, Task 1).

TDD approach: tests written first, then implementation.
"""

from datetime import datetime, timedelta, timezone

import pytest

from daily.briefing.models import RankedEmail
from daily.briefing.ranker import (
    DEADLINE_KEYWORDS,
    WEIGHT_CC,
    WEIGHT_DIRECT,
    WEIGHT_KEYWORD_HIT,
    WEIGHT_RECENCY_MAX,
    WEIGHT_VIP,
    _is_direct_recipient,
    rank_emails,
    score_email,
)
from daily.integrations.models import EmailMetadata


def make_email(
    message_id: str = "msg-001",
    thread_id: str = "thread-001",
    subject: str = "Hello",
    sender: str = "sender@example.com",
    recipient: str = "me@example.com",
    hours_ago: float = 2.0,
    is_unread: bool = True,
    labels: list[str] | None = None,
) -> EmailMetadata:
    """Helper to create EmailMetadata for tests."""
    now = datetime.now(tz=timezone.utc)
    return EmailMetadata(
        message_id=message_id,
        thread_id=thread_id,
        subject=subject,
        sender=sender,
        recipient=recipient,
        timestamp=now - timedelta(hours=hours_ago),
        is_unread=is_unread,
        labels=labels or ["INBOX"],
    )


def test_score_formula():
    """Test that score formula components sum correctly for a known input."""
    now = datetime.now(tz=timezone.utc)
    # Email 2 hours ago, direct recipient, non-VIP, urgent+deadline keywords
    email = make_email(
        subject="Urgent: deadline by EOD",
        sender="someone@example.com",
        recipient="me@example.com",
        hours_ago=2.0,
    )
    vip_senders: frozenset[str] = frozenset()
    thread_counts: dict[str, int] = {}

    score = score_email(email, vip_senders, "me@example.com", now, thread_counts)

    # sender_weight = WEIGHT_DIRECT (direct recipient, non-VIP)
    sender_weight = WEIGHT_DIRECT
    # keyword_weight: "urgent", "deadline", "by eod" all in subject
    keyword_hits = sum(
        1 for kw in DEADLINE_KEYWORDS if kw in "urgent: deadline by eod"
    )
    keyword_weight = keyword_hits * WEIGHT_KEYWORD_HIT
    # recency_weight: 2h old, max 24h linear decay
    hours_old = 2.0
    recency_weight = WEIGHT_RECENCY_MAX * max(0, (24 - hours_old) / 24)
    # thread_activity_weight: 0 (thread_count < 3)
    thread_weight = 0

    expected = sender_weight + keyword_weight + recency_weight + thread_weight

    assert score > 0
    assert abs(score - expected) < 0.01


def test_vip_override():
    """VIP sender with boring subject scores higher than non-VIP with urgent keywords.

    Both emails are the same age to isolate the sender weight effect.
    VIP sender weight (WEIGHT_VIP=40) must exceed WEIGHT_DIRECT + keyword weight
    for any typical keyword count. This validates D-03: VIP sender weight dominates.
    """
    now = datetime.now(tz=timezone.utc)
    vip_senders = frozenset({"vip@example.com"})
    thread_counts: dict[str, int] = {}

    # Both emails are same age — isolates sender weight vs keyword weight
    vip_email = make_email(
        subject="Hi there",
        sender="vip@example.com",
        recipient="me@example.com",
        hours_ago=1.0,
    )
    keyword_email = make_email(
        subject="Urgent action required deadline",
        sender="notvip@example.com",
        recipient="me@example.com",
        hours_ago=1.0,
    )

    vip_score = score_email(vip_email, vip_senders, "me@example.com", now, thread_counts)
    keyword_score = score_email(keyword_email, vip_senders, "me@example.com", now, thread_counts)

    assert vip_score > keyword_score, (
        f"VIP score {vip_score} should be > keyword score {keyword_score}"
    )


def test_rank_and_select_top_n(sample_emails, vip_senders):
    """rank_emails returns exactly top_n emails sorted by score descending."""
    ranked = rank_emails(sample_emails, vip_senders, "me@example.com", top_n=3)

    assert len(ranked) == 3
    assert all(isinstance(r, RankedEmail) for r in ranked)
    # Verify sorted descending
    scores = [r.score for r in ranked]
    assert scores == sorted(scores, reverse=True), f"Scores not descending: {scores}"


def test_recency_decay():
    """Email from 23 hours ago scores lower recency than email from 1 hour ago."""
    now = datetime.now(tz=timezone.utc)
    vip_senders: frozenset[str] = frozenset()
    thread_counts: dict[str, int] = {}

    recent_email = make_email(subject="Hello", sender="s@example.com", hours_ago=1.0)
    old_email = make_email(subject="Hello", sender="s@example.com", hours_ago=23.0)

    recent_score = score_email(
        recent_email, vip_senders, "me@example.com", now, thread_counts
    )
    old_score = score_email(
        old_email, vip_senders, "me@example.com", now, thread_counts
    )

    assert recent_score > old_score, (
        f"Recent score {recent_score} should be > old score {old_score}"
    )


def test_cc_vs_direct():
    """Email where user is in CC scores lower sender_weight than direct-to-user email."""
    now = datetime.now(tz=timezone.utc)
    vip_senders: frozenset[str] = frozenset()
    thread_counts: dict[str, int] = {}

    direct_email = make_email(
        subject="Hello",
        sender="s@example.com",
        recipient="me@example.com",
        hours_ago=1.0,
    )
    # CC email: user is not in the recipient To: field
    cc_email = make_email(
        subject="Hello",
        sender="s@example.com",
        recipient="team@example.com",  # user NOT in recipient field
        hours_ago=1.0,
    )

    direct_score = score_email(
        direct_email, vip_senders, "me@example.com", now, thread_counts
    )
    cc_score = score_email(
        cc_email, vip_senders, "me@example.com", now, thread_counts
    )

    assert direct_score > cc_score, (
        f"Direct score {direct_score} should be > CC score {cc_score}"
    )


def test_recipient_comparison_no_substring():
    """Verify per-address comparison: no substring false positives."""
    # "ice@example.com" should NOT match "alice@example.com"
    assert not _is_direct_recipient("ice@example.com", "alice@example.com"), (
        "ice@example.com should not match alice@example.com (substring false positive)"
    )

    # "bob@example.com" SHOULD match comma-separated "alice@example.com, bob@example.com"
    assert _is_direct_recipient("bob@example.com", "alice@example.com, bob@example.com"), (
        "bob@example.com should match alice@example.com, bob@example.com"
    )

    # "alice@example.com" SHOULD match
    assert _is_direct_recipient("alice@example.com", "alice@example.com"), (
        "alice@example.com should match alice@example.com"
    )

    # "evil@example.com" should NOT match "bob@evil@example.com" (malformed)
    assert not _is_direct_recipient("evil@example.com", "notevil@example.com"), (
        "evil@example.com should not match notevil@example.com"
    )


# --- RFC 2822 address normalization tests ---


def test_direct_recipient_rfc2822_bare_matches_formatted():
    """Bare user_email matches RFC 2822 formatted recipient 'Alice <alice@example.com>'."""
    assert _is_direct_recipient("alice@example.com", "Alice <alice@example.com>"), (
        "bare alice@example.com should match 'Alice <alice@example.com>'"
    )


def test_direct_recipient_rfc2822_formatted_matches_bare():
    """RFC 2822 formatted user_email matches bare recipient address."""
    assert _is_direct_recipient("Alice <alice@example.com>", "alice@example.com"), (
        "'Alice <alice@example.com>' should match bare alice@example.com"
    )


def test_direct_recipient_rfc2822_multiple_formatted_recipients():
    """User address found in comma-separated RFC 2822 formatted recipient list."""
    assert _is_direct_recipient(
        "alice@example.com",
        "Bob <bob@x.com>, Alice <alice@example.com>",
    ), "alice@example.com should match in RFC 2822 recipient list"


def test_direct_recipient_rfc2822_no_false_positive():
    """Different user does not falsely match RFC 2822 formatted recipient."""
    assert not _is_direct_recipient(
        "alice@example.com", "Bob <bob@example.com>"
    ), "alice@example.com should NOT match 'Bob <bob@example.com>'"


def test_direct_recipient_rfc2822_substring_rejection():
    """Substring of another address is not a match even with RFC 2822 normalization."""
    assert not _is_direct_recipient(
        "ice@example.com", "Alice <alice@example.com>"
    ), "ice@example.com should not match 'Alice <alice@example.com>'"


def test_score_email_weight_direct_with_rfc2822_recipient():
    """score_email returns WEIGHT_DIRECT when recipient is RFC 2822 formatted and user_email matches."""
    from datetime import datetime, timezone

    now = datetime.now(tz=timezone.utc)
    email = make_email(
        subject="Hello",
        sender="sender@example.com",
        recipient="User <user@x.com>",
        hours_ago=1.0,
    )
    vip_senders: frozenset[str] = frozenset()
    thread_counts: dict[str, int] = {}

    score = score_email(email, vip_senders, "user@x.com", now, thread_counts)

    # Sender weight should be WEIGHT_DIRECT, not WEIGHT_CC
    # Recency: 1h, WEIGHT_RECENCY_MAX * (23/24) ≈ 14.375
    recency = WEIGHT_RECENCY_MAX * (23 / 24)
    expected_min = WEIGHT_DIRECT + recency - 0.1
    assert score >= expected_min, (
        f"score {score} should include WEIGHT_DIRECT={WEIGHT_DIRECT} "
        f"(expected >= {expected_min})"
    )
