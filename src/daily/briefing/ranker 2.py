"""
Heuristic email ranker for the briefing pipeline.

Implements the scoring formula from D-04 with VIP override from D-03.
Ranks all emails and returns the top-N as RankedEmail objects.

Design decisions:
- VIP override guarantees max sender weight (D-03): VIP senders always score
  WEIGHT_VIP regardless of other factors.
- Recipient comparison uses per-address matching (not substring) to prevent
  false positives (e.g., "ice@example.com" in "alice@example.com").
- Thread activity adds weight when thread_id appears 3+ times in the batch.
"""

from datetime import datetime, timezone

from daily.briefing.models import RankedEmail
from daily.integrations.models import EmailMetadata

# Sender weight constants
WEIGHT_VIP = 40  # VIP override — always maximum sender weight (D-03)
WEIGHT_DIRECT = 10  # User is in the To: field
WEIGHT_CC = 2  # User is in CC/BCC or not in recipient field

# Keyword weight
WEIGHT_KEYWORD_HIT = 8  # Per keyword match in subject

# Recency weight (linear decay over 24h)
WEIGHT_RECENCY_MAX = 15  # Maximum recency weight (at 0 hours old)

# Thread activity weight
WEIGHT_THREAD_ACTIVE = 5  # Thread with 3+ emails in batch

# Keywords that indicate urgency/priority
DEADLINE_KEYWORDS = frozenset(
    [
        "urgent",
        "action required",
        "deadline",
        "by eod",
        "due today",
        "asap",
        "time sensitive",
        "response needed",
    ]
)


def _is_direct_recipient(user_email: str, recipient_field: str) -> bool:
    """Check if user_email appears as a complete address in recipient field.

    Splits recipient field by comma, strips whitespace, and compares each
    address individually. Prevents substring false positives.

    Args:
        user_email: The user's email address to look for.
        recipient_field: Comma-separated list of recipient addresses.

    Returns:
        True if user_email is one of the recipient addresses.
    """
    user_lower = user_email.lower().strip()
    recipients = [r.strip().lower() for r in recipient_field.split(",")]
    return user_lower in recipients


def score_email(
    email: EmailMetadata,
    vip_senders: frozenset[str],
    user_email: str,
    now: datetime,
    thread_counts: dict[str, int],
) -> float:
    """Score a single email using the D-04 heuristic formula.

    Formula: sender_weight + keyword_weight + recency_weight + thread_activity_weight

    Args:
        email: The email metadata to score.
        vip_senders: Set of VIP sender email addresses (D-03 override).
        user_email: The user's email address for recipient comparison.
        now: Current UTC datetime for recency calculation.
        thread_counts: Dict mapping thread_id to count in the current batch.

    Returns:
        Float score — higher means higher priority.
    """
    # Sender weight: VIP override takes precedence
    if email.sender.lower().strip() in {v.lower() for v in vip_senders}:
        sender_weight = WEIGHT_VIP
    elif _is_direct_recipient(user_email, email.recipient):
        sender_weight = WEIGHT_DIRECT
    else:
        sender_weight = WEIGHT_CC

    # Keyword weight: count matches in subject (case-insensitive)
    subject_lower = email.subject.lower()
    keyword_weight = sum(
        WEIGHT_KEYWORD_HIT for kw in DEADLINE_KEYWORDS if kw in subject_lower
    )

    # Recency weight: linear decay from WEIGHT_RECENCY_MAX at 0h to 0 at 24h
    # Ensure both datetimes are UTC-aware for comparison
    email_ts = email.timestamp
    if email_ts.tzinfo is None:
        email_ts = email_ts.replace(tzinfo=timezone.utc)
    now_aware = now
    if now_aware.tzinfo is None:
        now_aware = now_aware.replace(tzinfo=timezone.utc)

    hours_old = (now_aware - email_ts).total_seconds() / 3600
    recency_weight = WEIGHT_RECENCY_MAX * max(0.0, (24 - hours_old) / 24)

    # Thread activity weight: bonus when thread has 3+ emails in current batch
    thread_activity_weight = (
        WEIGHT_THREAD_ACTIVE if thread_counts.get(email.thread_id, 0) >= 3 else 0
    )

    return sender_weight + keyword_weight + recency_weight + thread_activity_weight


def rank_emails(
    emails: list[EmailMetadata],
    vip_senders: frozenset[str],
    user_email: str,
    top_n: int = 5,
) -> list[RankedEmail]:
    """Rank all emails by heuristic score and return the top-N.

    Per D-02/D-05: ranks all emails in the batch, returns top-N sorted
    by score descending as RankedEmail objects.

    Args:
        emails: All email metadata from the current fetch window.
        vip_senders: Set of VIP sender email addresses for override scoring.
        user_email: The user's email address for recipient comparison.
        top_n: Number of top-ranked emails to return (default 5).

    Returns:
        List of RankedEmail objects, sorted by score descending, length <= top_n.
    """
    now = datetime.now(tz=timezone.utc)

    # Compute thread counts for thread activity weighting
    thread_counts: dict[str, int] = {}
    for email in emails:
        thread_counts[email.thread_id] = thread_counts.get(email.thread_id, 0) + 1

    # Score all emails
    scored: list[tuple[float, EmailMetadata]] = []
    for email in emails:
        score = score_email(email, vip_senders, user_email, now, thread_counts)
        scored.append((score, email))

    # Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)

    # Return top-N as RankedEmail objects
    return [
        RankedEmail(metadata=email, score=score)
        for score, email in scored[:top_n]
    ]
