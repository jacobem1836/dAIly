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


# ─── sender_multipliers tests ──────────────────────────────────────────────────


def test_rank_emails_no_multipliers_unchanged():
    """rank_emails without sender_multipliers and with empty dict produce identical ordering.

    Scores may differ by tiny floating-point amounts due to recency decay being
    computed from wall-clock time between the two calls. We compare ordering and
    relative score ratios rather than exact values.
    """
    emails = [
        make_email(message_id="msg-001", sender="alice@example.com", hours_ago=1.0),
        make_email(message_id="msg-002", sender="bob@example.com", hours_ago=2.0),
    ]
    vip_senders: frozenset[str] = frozenset()

    ranked_none = rank_emails(emails, vip_senders, "me@example.com", top_n=2)
    ranked_empty = rank_emails(emails, vip_senders, "me@example.com", top_n=2, sender_multipliers={})

    # Ordering must be identical
    assert [r.metadata.message_id for r in ranked_none] == [r.metadata.message_id for r in ranked_empty]
    # Scores should be very close (within 0.1 to account for wall-clock recency drift)
    for r_none, r_empty in zip(ranked_none, ranked_empty):
        assert abs(r_none.score - r_empty.score) < 0.1


def test_rank_emails_unknown_sender_defaults_to_one():
    """Sender not in multipliers dict receives a multiplier of 1.0 (score within tolerance)."""
    email = make_email(message_id="msg-001", sender="alice@example.com", hours_ago=1.0)
    vip_senders: frozenset[str] = frozenset()

    ranked_no_mults = rank_emails([email], vip_senders, "me@example.com", top_n=1)
    ranked_with_mults = rank_emails(
        [email], vip_senders, "me@example.com", top_n=1,
        sender_multipliers={"other@example.com": 2.0},
    )

    # Scores may differ slightly due to recency drift between calls; alice gets no multiplier
    assert abs(ranked_no_mults[0].score - ranked_with_mults[0].score) < 0.1


def test_rank_emails_multiplier_scales_score():
    """Sender multiplier 2.0 doubles the heuristic score."""
    now = datetime.now(tz=timezone.utc)
    email = make_email(message_id="msg-001", sender="alice@example.com", hours_ago=1.0)
    vip_senders: frozenset[str] = frozenset()
    thread_counts: dict[str, int] = {}

    heuristic_score = score_email(email, vip_senders, "me@example.com", now, thread_counts)

    ranked = rank_emails(
        [email], vip_senders, "me@example.com", top_n=1,
        sender_multipliers={"alice@example.com": 2.0},
    )

    assert abs(ranked[0].score - heuristic_score * 2.0) < 0.01


def test_rank_emails_multiplier_reorders():
    """Higher multiplier on a lower-scoring sender causes it to rank above equal-scored sender."""
    # Both emails are from same hours_ago so recency is equal; same subject (no keywords);
    # same recipient field (CC) so sender weight is equal — heuristic scores are equal.
    email_alice = make_email(
        message_id="msg-alice",
        sender="alice@example.com",
        recipient="team@example.com",
        hours_ago=2.0,
    )
    email_bob = make_email(
        message_id="msg-bob",
        sender="bob@example.com",
        recipient="team@example.com",
        hours_ago=2.0,
    )
    vip_senders: frozenset[str] = frozenset()

    ranked = rank_emails(
        [email_alice, email_bob], vip_senders, "me@example.com", top_n=2,
        sender_multipliers={"bob@example.com": 3.0, "alice@example.com": 1.0},
    )

    assert ranked[0].metadata.message_id == "msg-bob", (
        f"bob (multiplier 3.0) should rank first, got: {ranked[0].metadata.message_id}"
    )


def test_rank_emails_sender_normalisation():
    """Sender key lookup normalises email: 'Alice@Example.com ' matches 'alice@example.com'."""
    email = make_email(
        message_id="msg-001",
        sender="Alice@Example.com ",  # mixed case with trailing space
        hours_ago=1.0,
    )
    vip_senders: frozenset[str] = frozenset()

    ranked_no_mults = rank_emails([email], vip_senders, "me@example.com", top_n=1)
    ranked_with_mults = rank_emails(
        [email], vip_senders, "me@example.com", top_n=1,
        sender_multipliers={"alice@example.com": 2.0},
    )

    # Multiplier 2.0 should be applied — score should be doubled
    assert abs(ranked_with_mults[0].score - ranked_no_mults[0].score * 2.0) < 0.01
