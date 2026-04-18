"""BriefingItem model and item list builder for signal tracking.

Each briefing item maps to a section of the narrative (by sentence range)
and carries the sender identity needed for adaptive ranking signals.

Per D-02: item list is cached in Redis alongside the narrative.
Per Pitfall 4: all fields are primitives (str, int) for LangGraph JSON serialisation.
Per Pitfall 1/A1: `sender` field carries the sender email for ranker aggregation.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from daily.briefing.models import BriefingContext


class BriefingItem(BaseModel):
    """A single briefing section with sender tracking for signal capture.

    Fields are primitive types only (Pitfall 4: LangGraph checkpoint serialisation).
    """

    item_id: str          # e.g. "email-0", "calendar-1", "slack-2"
    type: str             # "email" | "calendar" | "slack"
    sender: str           # sender email address (for ranker aggregation per D-05)
    sentence_range_start: int
    sentence_range_end: int


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences — same regex as voice/loop.py.

    Extracted here so pipeline and voice loop use identical splitting
    (Pitfall 5: cursor sync requires same split function).
    """
    parts = re.split(r'(?<=[.?!])\s+', text)
    return [s.strip() for s in parts if s.strip()]


def build_briefing_items(context: BriefingContext, narrative: str) -> list[BriefingItem]:
    """Build a BriefingItem list from the briefing context and generated narrative.

    Assigns sentence ranges by splitting the narrative into sentences and
    distributing them across items proportionally. Items are ordered:
    emails first, then calendar, then slack — matching the narrator's
    typical output order.

    If the narrative has fewer sentences than items, remaining items get
    empty ranges. If more sentences than items, the last item absorbs
    the remainder.

    Args:
        context: BriefingContext with ranked emails, calendar, and slack.
        narrative: The generated narrative text.

    Returns:
        List of BriefingItem with sentence ranges assigned.
    """
    sentences = _split_sentences(narrative)
    total_sentences = len(sentences)

    # Build raw item list (ordered: emails, calendar, slack)
    raw_items: list[dict] = []

    for i, email in enumerate(context.emails):
        raw_items.append({
            "item_id": f"email-{i}",
            "type": "email",
            "sender": email.metadata.sender.lower().strip(),
        })

    for i, event in enumerate(context.calendar.events):
        # CalendarEvent has no organizer field — use first attendee as sender proxy
        # or empty string if no attendees present.
        organizer = event.attendees[0] if event.attendees else ""
        raw_items.append({
            "item_id": f"calendar-{i}",
            "type": "calendar",
            "sender": organizer.lower().strip(),
        })

    for i, msg in enumerate(context.slack.messages):
        # MessageMetadata uses sender_id (not sender)
        raw_items.append({
            "item_id": f"slack-{i}",
            "type": "slack",
            "sender": msg.sender_id.lower().strip(),
        })

    if not raw_items:
        return []

    # Distribute sentences across items proportionally
    per_item = max(1, total_sentences // len(raw_items)) if raw_items else 0
    items: list[BriefingItem] = []
    cursor = 0
    for idx, raw in enumerate(raw_items):
        start = cursor
        if idx == len(raw_items) - 1:
            # Last item absorbs remaining sentences
            end = total_sentences
        else:
            end = min(cursor + per_item, total_sentences)
        items.append(BriefingItem(
            item_id=raw["item_id"],
            type=raw["type"],
            sender=raw["sender"],
            sentence_range_start=start,
            sentence_range_end=end,
        ))
        cursor = end

    return items
