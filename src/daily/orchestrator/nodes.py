"""Orchestrator graph node functions.

respond_node: GPT-4.1 mini — quick conversational follow-ups (D-02).
summarise_thread_node: GPT-4.1 — reasoning-heavy thread summarisation (D-02, BRIEF-07).
draft_node: Full LLM draft generation with sent-email style matching (Plan 02).
approval_node: Human-in-the-loop interrupt gate using langgraph.types.interrupt (T-04-02).
execute_node: Executes approved action (stub in Plan 01) and fire-and-forget logs.

Security boundaries enforced in this module:
  SEC-05: response_format=json_object, no tools= parameter, OrchestratorIntent validation
  SEC-02/SEC-04: raw email bodies pass through summarise_and_redact() before any state write
  T-03-06: No tools= on any LLM call — prevents privilege escalation
  T-03-07: raw_body is a local variable only, never assigned to state fields
  T-04-02: No direct edge START -> execute; approval_node interrupt() fires before any execution
  T-04-07: Sent email bodies pass through summarise_and_redact() before inclusion in draft prompt
  T-04-09: No tools= parameter on draft_node LLM call; response_format=json_object only

Signal/action capture:
  D-08: append_signal / append_action_log wrapped in asyncio.create_task() — fire-and-forget.
"""

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta

from langchain_core.messages import AIMessage
from langgraph.types import interrupt
from openai import AsyncOpenAI

from daily.actions.base import BLOCKED_ACTION_TYPES, ActionDraft, ActionType
from daily.briefing.redactor import summarise_and_redact
from daily.orchestrator.models import OrchestratorIntent
from daily.orchestrator.session import get_email_adapters
from daily.orchestrator.state import SessionState
from daily.profile.memory import clear_all_memories, delete_memory_fact, list_all_memories
from daily.profile.service import upsert_preference
from daily.profile.signals import SignalType

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"[\w.+\-]+@[\w.\-]+")


def _extract_email(header_value: str) -> str:
    """Extract bare email address from an RFC 2822 From/To header value.

    Handles both "Name <email@example.com>" and bare "email@example.com" forms.
    Returns the first email address found, or the original string if none matches.
    """
    m = _EMAIL_RE.search(header_value)
    return m.group(0) if m else header_value


def _openai_client() -> AsyncOpenAI:
    """Build AsyncOpenAI with explicit key from Settings (never relies on env)."""
    from daily.config import Settings  # noqa: PLC0415

    return AsyncOpenAI(api_key=Settings().openai_api_key)


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

RESPOND_SYSTEM_PROMPT = (
    "You are a personal briefing assistant. The user is asking about their morning briefing.\n"
    "Answer based on the briefing context provided. Be concise and conversational.\n\n"
    "BRIEFING CONTEXT:\n{briefing_narrative}\n\n"
    "USER PREFERENCES: tone={tone}, length={length}\n\n"
    'Output MUST be valid JSON: {{"action": "answer", "narrative": "your response text", "target_id": null}}'
)

SUMMARISE_SYSTEM_PROMPT = (
    "You are a personal briefing assistant. Summarise the following email thread "
    "for the user. Be concise, highlight key decisions and action items.\n\n"
    "REDACTED THREAD CONTENT:\n{redacted_content}\n\n"
    'Output MUST be valid JSON: {{"action": "summarise_thread", '
    '"narrative": "your summary", "target_id": "{target_id}"}}'
)

DRAFT_SYSTEM_PROMPT = (
    "You are a personal assistant drafting a {action_type} on behalf of the user.\n"
    "Match the user's writing style based on these recent sent emails:\n\n"
    "{style_examples}\n\n"
    "AVAILABLE EMAILS (use to identify the correct recipient and thread):\n"
    "{email_context}\n\n"
    "USER PREFERENCES: tone={tone}\n"
    "USER INSTRUCTION: {instruction}\n\n"
    "BRIEFING CONTEXT (for reference):\n{briefing_narrative}\n\n"
    "When the user wants to reply to an email, match their description to the correct "
    "email from the AVAILABLE EMAILS list and use that email's sender as the recipient. "
    "Include the thread_id and message_id from the matched email in your output.\n\n"
    "Output MUST be valid JSON with these fields:\n"
    '{{"recipient": "email@example.com or null", "subject": "Re: ... or null", '
    '"body": "the full draft text", "thread_id": "matched thread_id or null", '
    '"message_id": "matched message_id or null", '
    '"event_title": "null or title", '
    '"start_dt": "null or ISO datetime", "end_dt": "null or ISO datetime", '
    '"attendees": []}}'
)

# Maximum number of sent emails to use as style examples (D-06)
_MAX_STYLE_EXAMPLES = 5

# Phase 12 CONV-03: tone compression triggers (D-07)
COMPRESSION_PHRASES = [
    "i'm in a rush",
    "keep it brief",
    "quick version",
    "short version",
    "make it snappy",
    "i'm busy",
]

# Implicit trigger threshold: consecutive short messages (D-07)
_IMPLICIT_TONE_MIN_TURNS = 2
_IMPLICIT_TONE_MAX_WORDS = 5


def _format_email_context(email_context: list[dict]) -> str:
    """Format email metadata list into a compact table for the LLM prompt.

    Only metadata fields are included — never raw bodies (SEC-04).

    Args:
        email_context: List of email metadata dicts with sender, subject,
                       thread_id, and message_id keys.

    Returns:
        A numbered, human-readable string for inclusion in the LLM prompt,
        or a placeholder string if the list is empty.
    """
    if not email_context:
        return "(no emails available)"
    lines = []
    for i, e in enumerate(email_context, 1):
        lines.append(
            f"{i}. From: {e['sender']} | Subject: {e['subject']} | "
            f"thread_id: {e['thread_id']} | message_id: {e['message_id']}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Node functions
# ---------------------------------------------------------------------------


async def respond_node(state: SessionState) -> dict:
    """Answer a conversational follow-up using GPT-4.1 mini (D-02).

    Validates LLM output as OrchestratorIntent (SEC-05 — no arbitrary actions).
    Captures follow_up signal as fire-and-forget (D-08).

    No `tools=` parameter — SEC-05/T-03-06 enforcement.

    Args:
        state: Current SessionState with messages and briefing_narrative.

    Returns:
        State update dict with AIMessage containing intent.narrative.
    """
    # Build conversation history from messages (exclude last human message — it
    # will be added as the final user message)
    conversation = []
    for msg in state.messages:
        if hasattr(msg, "type"):
            role = "user" if msg.type == "human" else "assistant"
        else:
            role = "user"
        conversation.append({"role": role, "content": msg.content})

    # Phase 9 INTEL-02: inject recalled memories into live-session system prompt.
    memory_preamble = ""
    if state.user_memories:
        memory_lines = "\n".join(f"- {m}" for m in state.user_memories)
        memory_preamble = (
            "User memories (facts recalled from previous sessions):\n"
            f"{memory_lines}\n\n"
            "Incorporate relevant memories naturally when answering. "
            "Do not invent memories.\n\n"
        )

    # Phase 12 CONV-03: tone override takes priority over preference (D-09)
    effective_tone = state.preferences.get("tone", "conversational")
    effective_length = state.preferences.get("briefing_length", "standard")
    state_updates: dict = {}

    if state.tone_override == "brief":
        # Already triggered — keep compressed
        effective_tone = "brief"
        effective_length = "short"
    elif not state.tone_override:
        # Check explicit triggers (D-07: substring match, D-08: pre-LLM)
        last_msg_lower = state.messages[-1].content.lower() if state.messages else ""
        explicit_trigger = any(phrase in last_msg_lower for phrase in COMPRESSION_PHRASES)

        # Check implicit triggers (D-07: < 5 words for 2 consecutive user turns)
        human_messages = [m for m in state.messages if hasattr(m, "type") and m.type == "human"]
        implicit_trigger = (
            len(human_messages) >= _IMPLICIT_TONE_MIN_TURNS
            and all(
                len(human_messages[-(i + 1)].content.split()) < _IMPLICIT_TONE_MAX_WORDS
                for i in range(_IMPLICIT_TONE_MIN_TURNS)
            )
        )

        if explicit_trigger or implicit_trigger:
            state_updates["tone_override"] = "brief"
            effective_tone = "brief"
            effective_length = "short"

    system_content = memory_preamble + RESPOND_SYSTEM_PROMPT.format(
        briefing_narrative=state.briefing_narrative or "(no briefing loaded)",
        tone=effective_tone,
        length=effective_length,
    )

    if effective_tone == "brief":
        system_content += (
            "\n\nIMPORTANT: The user is in a rush. Be compressed and direct. "
            "Max 2 sentences per response. Skip pleasantries."
        )

    client = _openai_client()
    try:
        response = await client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": system_content},
                *conversation,
            ],
            response_format={"type": "json_object"},
            max_tokens=400,
        )
        raw_content = response.choices[0].message.content
        intent = OrchestratorIntent.model_validate_json(raw_content)
        narrative = intent.narrative
    except Exception as exc:
        logger.warning("respond_node: LLM output failed validation: %s", exc)
        narrative = "I couldn't process that. Could you rephrase?"

    # Fire-and-forget signal capture (D-08) — does not block voice path
    if state.active_user_id:
        asyncio.create_task(
            _capture_signal(state.active_user_id, SignalType.follow_up)
        )

    return {"messages": [AIMessage(content=narrative)], **state_updates}


async def resume_briefing_node(state: SessionState) -> dict:
    """Resume briefing delivery from the stored cursor position.

    Returns a confirmation message. The voice loop checks briefing_cursor
    after speaking this message and re-enters the sentence iteration loop.
    TTS orchestration stays in voice/loop.py — this node only provides
    the verbal cue (RESEARCH.md Pattern 5, simpler alternative).

    Phase 12 CONV-01/CONV-02: explicit resume path via D-03 keywords.

    Args:
        state: Current SessionState with briefing_cursor set.

    Returns:
        State update dict with AIMessage confirmation. briefing_cursor
        is NOT cleared here — the voice loop clears it after delivery.
    """
    if state.briefing_cursor is None:
        return {"messages": [AIMessage(content="There's no briefing to resume — it was fully delivered.")]}

    return {"messages": [AIMessage(content="Resuming your briefing now.")]}


# ---------------------------------------------------------------------------
# Phase 13 nodes: skip, re_request (signal capture)
# ---------------------------------------------------------------------------


def _get_current_item_sender(state: SessionState) -> str | None:
    """Extract sender from the current briefing item, or None if unavailable.

    Defensive: returns None if briefing_items is empty or current_item_index
    is out of range (e.g. old cached briefing from before Phase 13).
    Per Pitfall 2: signals fire with target_id=None rather than crashing.
    """
    if not state.briefing_items:
        return None
    idx = min(state.current_item_index, len(state.briefing_items) - 1)
    item = state.briefing_items[idx]
    # briefing_items stores dicts (not BriefingItem) for LangGraph serialisation
    if isinstance(item, dict):
        return item.get("sender")
    return getattr(item, "sender", None)


async def skip_node(state: SessionState) -> dict:
    """Handle explicit skip intent — fire skip signal and acknowledge.

    Per D-01: "skip", "next", "move on" route here.
    Fires SignalType.skip with the current item's sender as target_id
    (per Pitfall 1/A1: target_id = sender email for ranker aggregation).
    Uses _capture_signal fire-and-forget pattern (D-08).

    Args:
        state: Current SessionState with briefing_items and current_item_index.

    Returns:
        Dict with acknowledgement message.
    """
    sender = _get_current_item_sender(state)
    if state.active_user_id:
        asyncio.create_task(
            _capture_signal(state.active_user_id, SignalType.skip, target_id=sender)
        )
    return {"messages": [AIMessage(content="Skipping to the next item.")]}


async def re_request_node(state: SessionState) -> dict:
    """Handle re_request intent — fire signal and re-speak current item.

    Per D-04: "repeat that", "say that again" route here.
    Fires SignalType.re_request with the current item's sender as target_id.
    Returns the current item's sentences for re-delivery.

    Args:
        state: Current SessionState with briefing_items and current_item_index.

    Returns:
        Dict with the current item's narrative content for re-speaking.
    """
    sender = _get_current_item_sender(state)
    if state.active_user_id:
        asyncio.create_task(
            _capture_signal(state.active_user_id, SignalType.re_request, target_id=sender)
        )

    # Re-speak the current item's sentences from the narrative
    content = "Sure, let me repeat that."
    if state.briefing_narrative and state.briefing_items:
        from daily.briefing.items import _split_sentences  # noqa: PLC0415
        sentences = _split_sentences(state.briefing_narrative)
        idx = min(state.current_item_index, len(state.briefing_items) - 1)
        item = state.briefing_items[idx]
        if isinstance(item, dict):
            start = item.get("sentence_range_start", 0)
            end = item.get("sentence_range_end", len(sentences))
        else:
            start = getattr(item, "sentence_range_start", 0)
            end = getattr(item, "sentence_range_end", len(sentences))
        item_sentences = sentences[start:end]
        if item_sentences:
            content = "Sure, let me repeat that. " + " ".join(item_sentences)

    return {"messages": [AIMessage(content=content)]}


def _resolve_message_id(user_query: str, email_context: list[dict]) -> str | None:
    """Match user's natural language query against email_context metadata.

    Searches subject and sender fields (case-insensitive substring match).
    Returns the message_id of the first matching email, or None if no match.

    Args:
        user_query: The user's message text describing which email to summarise.
        email_context: List of email metadata dicts with message_id, subject, sender keys.

    Returns:
        The message_id string of the best match, or None if no email matches.
    """
    query_lower = user_query.lower()
    for email in email_context:
        subject = email.get("subject", "").lower()
        sender = email.get("sender", "").lower()
        if subject and subject in query_lower:
            return email["message_id"]
        if sender and sender in query_lower:
            return email["message_id"]
    # Second pass: check if any word from the query appears in subject/sender
    query_words = [w for w in query_lower.split() if len(w) > 3]
    for email in email_context:
        subject = email.get("subject", "").lower()
        sender = email.get("sender", "").lower()
        for word in query_words:
            if word in subject or word in sender:
                return email["message_id"]
    return None


async def summarise_thread_node(state: SessionState) -> dict:
    """Summarise an email thread using GPT-4.1 (D-02, BRIEF-07).

    Security boundaries:
    - Fetches email body via adapter from the adapter registry
    - Passes raw_body through summarise_and_redact() BEFORE any state write (SEC-04)
    - raw_body is a local variable only — never assigned to state fields (T-03-07)
    - No `tools=` parameter (SEC-05/T-03-06)
    - OrchestratorIntent validates LLM output (D-03)

    Fire-and-forget expand signal via asyncio.create_task() (D-08).

    Args:
        state: Current SessionState with messages.

    Returns:
        State update dict with AIMessage containing the thread summary.
    """
    adapters = get_email_adapters()
    if not adapters:
        return {
            "messages": [
                AIMessage(
                    content=(
                        "No email accounts connected. Connect an account with "
                        "`daily connect gmail` or `daily connect outlook` first."
                    )
                )
            ]
        }

    # Resolve message_id from email_context (D-07, D-09)
    last_content = state.messages[-1].content if state.messages else ""
    message_id = _resolve_message_id(last_content, state.email_context)

    if message_id is None:
        # D-08: No match found — return clear user-facing error
        return {
            "messages": [
                AIMessage(
                    content=(
                        "I can't find that email \u2014 try asking during or right "
                        "after your briefing when I have context loaded."
                    )
                )
            ]
        }

    client = _openai_client()

    try:
        # Fetch raw body via first available email adapter
        raw_body = await adapters[0].get_email_body(message_id)

        # CRITICAL (SEC-04/T-03-07): raw_body MUST pass through summarise_and_redact
        # before being used anywhere. raw_body is a local variable — never assigned
        # to any state field.
        redacted_content = await summarise_and_redact(raw_body, client)

        # Generate thread summary with GPT-4.1 (full model — D-02)
        response = await client.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {
                    "role": "system",
                    "content": SUMMARISE_SYSTEM_PROMPT.format(
                        redacted_content=redacted_content,
                        target_id=message_id,
                    ),
                },
                {"role": "user", "content": "Summarise this thread."},
            ],
            response_format={"type": "json_object"},
            max_tokens=600,
        )
        raw_response = response.choices[0].message.content
        intent = OrchestratorIntent.model_validate_json(raw_response)
        narrative = intent.narrative

    except Exception as exc:
        logger.warning("summarise_thread_node: error: %s", exc)
        narrative = "I had trouble fetching that thread. Please try again."

    # Fire-and-forget expand signal (D-08)
    if state.active_user_id:
        asyncio.create_task(
            _capture_signal(state.active_user_id, SignalType.expand, target_id=message_id)
        )

    return {"messages": [AIMessage(content=narrative)]}


async def _capture_signal(
    user_id: int,
    signal_type: SignalType,
    target_id: str | None = None,
) -> None:
    """Fire-and-forget signal capture. Creates its own DB session.

    Called via asyncio.create_task() so it never blocks the graph node's
    return path (D-08 fire-and-forget pattern).

    Args:
        user_id: User to record the signal for.
        signal_type: The interaction signal to record.
        target_id: Optional reference to an email or message.
    """
    try:
        from daily.db.engine import async_session
        from daily.profile.signals import append_signal

        async with async_session() as session:
            await append_signal(
                user_id=user_id,
                signal_type=signal_type,
                session=session,
                target_id=target_id,
            )
    except Exception as exc:
        # Signal capture failure must never propagate to the graph
        logger.warning("_capture_signal: failed to write signal: %s", exc)


# ---------------------------------------------------------------------------
# Phase 4 nodes: draft, approval, execute
# ---------------------------------------------------------------------------


def _infer_action_type(instruction: str) -> ActionType:
    """Infer ActionType from the user's instruction keywords.

    Priority order (most specific first):
    - reschedule/move -> reschedule_event
    - schedule/book/meeting/create event -> schedule_event
    - slack/message/dm -> draft_message
    - reply/email -> draft_email (default for email-related)

    Args:
        instruction: The user's natural language instruction.

    Returns:
        The most appropriate ActionType for this instruction.
    """
    lowered = instruction.lower()

    if any(kw in lowered for kw in ("reschedule", "move meeting", "move the meeting")):
        return ActionType.reschedule_event

    if any(kw in lowered for kw in ("schedule", "book", "create event", "cancel meeting")):
        return ActionType.schedule_event

    if any(kw in lowered for kw in ("slack", "message", " dm ", "direct message")):
        return ActionType.draft_message

    # Default: email draft
    return ActionType.draft_email


async def _fetch_style_examples(client: AsyncOpenAI) -> str:
    """Fetch and redact recent sent emails for use as writing style examples.

    Security (T-04-07): ALL email bodies pass through summarise_and_redact()
    before being included in the LLM prompt. Raw bodies are local variables only.

    Args:
        client: AsyncOpenAI client for redaction calls.

    Returns:
        Formatted string of redacted style examples, or empty string if unavailable.
    """
    adapters = get_email_adapters()
    if not adapters:
        return ""

    try:
        since = datetime.now() - timedelta(days=30)
        # Fetch recent emails for style examples
        page = await adapters[0].list_emails(since=since)
        # Limit to _MAX_STYLE_EXAMPLES to avoid bloating the prompt
        sent_emails = page.emails[:_MAX_STYLE_EXAMPLES]

        if not sent_emails:
            return ""

        redacted_examples = []
        for email_meta in sent_emails:
            try:
                # raw_body is a local variable only — never assigned to state (T-04-07)
                raw_body = await adapters[0].get_email_body(email_meta.message_id)
                redacted = await summarise_and_redact(raw_body, client)
                if redacted:
                    redacted_examples.append(f"---\n{redacted}")
            except Exception as exc:
                logger.debug("_fetch_style_examples: skipped email %s: %s", email_meta.message_id, exc)
                continue

        return "\n".join(redacted_examples)

    except Exception as exc:
        logger.warning("_fetch_style_examples: adapter fetch failed: %s", exc)
        return ""


async def draft_node(state: SessionState) -> dict:
    """Generate a draft action via GPT-4.1 with sent-email style matching (Plan 02).

    Replaces the Plan 01 stub with full LLM drafting:
    1. Extracts instruction from last human message.
    2. Infers action type from instruction keywords.
    3. Fetches and redacts recent sent emails as style examples (D-06, T-04-07).
    4. Builds DRAFT_SYSTEM_PROMPT with tone, instruction, and style examples.
    5. Calls GPT-4.1 with response_format=json_object and NO tools= (T-04-09).
    6. Parses JSON response into ActionDraft.

    Security boundaries:
    - T-04-07: All sent email bodies pass through summarise_and_redact() before LLM prompt
    - T-04-08: JSON output mapped to ActionDraft Pydantic model — invalid fields rejected
    - T-04-09: No tools= parameter; response_format=json_object only (SEC-05/T-03-06)

    Args:
        state: Current SessionState with messages, preferences, and briefing_narrative.

    Returns:
        State update dict with pending_action set to an ActionDraft, and an AIMessage.
        On error: returns error message without setting pending_action.
    """
    # Check if this is an edit loop re-entry (approval_decision starts with "edit:")
    edit_instruction = None
    if state.approval_decision and state.approval_decision.startswith("edit:"):
        edit_instruction = state.approval_decision[len("edit:"):]

    # Extract instruction from last human message (or use edit instruction for re-draft)
    instruction = state.messages[-1].content if state.messages else "draft an email"

    # Infer action type: reuse existing type on edit, infer from instruction on fresh draft
    if edit_instruction and state.pending_action:
        action_type = state.pending_action.action_type
        # Combine edit instruction with original draft context for re-drafting
        instruction = (
            f"Original draft:\n{state.pending_action.body}\n\n"
            f"Edit instruction: {edit_instruction}"
        )
    else:
        # Infer action type from instruction keywords
        action_type = _infer_action_type(instruction)

    tone = state.preferences.get("tone", "conversational")
    briefing_narrative = state.briefing_narrative or "(no briefing loaded)"

    client = _openai_client()

    # Fetch style examples (T-04-07: all bodies redacted before prompt inclusion)
    style_examples = await _fetch_style_examples(client)

    # Populate email context for recipient/thread matching
    # Fallback: if email_context is empty (e.g. non-briefing session), fetch live
    email_ctx = state.email_context
    if not email_ctx:
        adapters = get_email_adapters()
        if adapters:
            try:
                page = await adapters[0].list_emails(since=datetime.now() - timedelta(days=7))
                email_ctx = [
                    {
                        "message_id": e.message_id,
                        "thread_id": e.thread_id,
                        "subject": e.subject,
                        "sender": _extract_email(e.sender),
                        "recipient": _extract_email(e.recipient),
                        "timestamp": e.timestamp.isoformat(),
                    }
                    for e in page.emails
                ]
                logger.warning("draft_node: fallback fetched %d emails", len(email_ctx))
            except Exception as exc:
                logger.warning("draft_node: fallback email fetch failed: %s", exc)
                email_ctx = []

    logger.warning("draft_node: email_ctx has %d entries", len(email_ctx))
    email_context_str = _format_email_context(email_ctx)
    logger.warning("draft_node: email_context_str preview: %s", email_context_str[:200])

    # Build system prompt
    system_content = DRAFT_SYSTEM_PROMPT.format(
        action_type=action_type.value.replace("_", " "),
        style_examples=style_examples or "(no style examples available)",
        email_context=email_context_str,
        tone=tone,
        instruction=instruction,
        briefing_narrative=briefing_narrative,
    )

    try:
        # GPT-4.1 (full model — D-02 quality requirement for drafting)
        # NO tools= parameter (T-04-09/SEC-05/T-03-06)
        response = await client.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": instruction},
            ],
            response_format={"type": "json_object"},
            max_tokens=800,
        )
        raw_content = response.choices[0].message.content

        # T-04-08: Parse and validate via Pydantic — invalid fields rejected
        parsed = json.loads(raw_content)

        # Handle null values from LLM output
        start_dt = None
        end_dt = None
        if parsed.get("start_dt") and parsed["start_dt"] not in (None, "null", ""):
            try:
                start_dt = datetime.fromisoformat(parsed["start_dt"])
            except (ValueError, TypeError):
                start_dt = None
        if parsed.get("end_dt") and parsed["end_dt"] not in (None, "null", ""):
            try:
                end_dt = datetime.fromisoformat(parsed["end_dt"])
            except (ValueError, TypeError):
                end_dt = None

        attendees = parsed.get("attendees") or []
        if not isinstance(attendees, list):
            attendees = []

        draft = ActionDraft(
            action_type=action_type,
            recipient=parsed.get("recipient") or None,
            subject=parsed.get("subject") or None,
            body=parsed.get("body") or "(no content)",
            thread_id=parsed.get("thread_id") or None,
            thread_message_id=parsed.get("message_id") or None,
            event_title=parsed.get("event_title") or None,
            start_dt=start_dt,
            end_dt=end_dt,
            attendees=attendees,
        )

        action_label = action_type.value.replace("_", " ")
        return {
            "pending_action": draft,
            "approval_decision": None,  # Clear so next approval loop starts fresh
            "messages": [AIMessage(content=f"Here's what I'd {action_label}:")],
        }

    except Exception as exc:
        logger.warning("draft_node: failed to generate draft: %s", exc)
        return {
            "messages": [
                AIMessage(
                    content="I had trouble drafting that. Could you try rephrasing?"
                )
            ]
        }


async def approval_node(state: SessionState) -> dict:
    """Human-in-the-loop approval gate using LangGraph interrupt() (T-04-02).

    Phase 11 autonomy pre-check (D-05, D-06):
      1. If action_type is in BLOCKED_ACTION_TYPES -> always interrupt (never bypass).
      2. Else if user's autonomy_levels has this type set to "auto" -> skip interrupt,
         return confirm directly with auto_executed flag.
      3. Otherwise (approve, suggest, or missing) -> interrupt as before.

    CRITICAL: interrupt() must NOT be wrapped in try/except. LangGraph uses
    a special exception mechanism internally — catching it would break the
    human-in-the-loop pattern entirely.
    """
    action_type = state.pending_action.action_type

    # --- Phase 11 autonomy pre-check (D-05, D-06) ---
    # Blocked types ALWAYS require approval — no config can override this.
    if action_type not in BLOCKED_ACTION_TYPES:
        autonomy_levels = state.preferences.get("autonomy_levels", {})
        level = autonomy_levels.get(action_type.value, "approve")
        if level == "auto":
            return {"approval_decision": "confirm", "auto_executed": True}
        # "suggest" treated as "approve" in Phase 11 (D-09) — fall through to interrupt

    # --- Existing approval gate (unchanged from v1.0) ---
    payload = {
        "preview": state.pending_action.card_text(),
        "action_type": state.pending_action.action_type.value,
    }
    decision = interrupt(payload)
    return {"approval_decision": decision}


async def _build_executor_for_type(
    action_type: ActionType,
    user_id: int,
) -> "ActionExecutor":
    """Build the correct ActionExecutor for a given action_type and user.

    Provider routing for email actions:
      - Queries integration_tokens for the user to determine connected provider.
      - If user has 'microsoft' token -> OutlookExecutor
      - If user has 'google' token -> GmailExecutor
      - If both, prefers most recently updated token.

    Other action types:
      - draft_message -> SlackExecutor
      - schedule_event / reschedule_event -> GoogleCalendarExecutor

    Decrypts token in-memory only at call time (T-04-13).
    Populates known_addresses from recent email metadata via adapter.

    Args:
        action_type: The type of action to execute.
        user_id: ID of the user whose tokens and contacts to load.

    Returns:
        A concrete ActionExecutor ready for validate() and execute().

    Raises:
        ValueError: If no suitable integration token is found for the user.
    """
    from sqlalchemy import select

    from daily.actions.google.calendar import GoogleCalendarExecutor
    from daily.actions.google.email import GmailExecutor
    from daily.actions.microsoft.executor import OutlookExecutor
    from daily.actions.slack.executor import SlackExecutor
    from daily.config import Settings
    from daily.db.engine import async_session
    from daily.db.models import IntegrationToken
    from daily.vault import decrypt_token

    settings = Settings()
    import base64
    vault_key = base64.urlsafe_b64decode(settings.vault_key) if settings.vault_key else b""

    if action_type in (ActionType.draft_email, ActionType.compose_email):
        async with async_session() as session:
            stmt = (
                select(IntegrationToken)
                .where(
                    IntegrationToken.user_id == user_id,
                    IntegrationToken.provider.in_(["google", "microsoft"]),
                )
                .order_by(IntegrationToken.updated_at.desc())
            )
            result = await session.execute(stmt)
            tokens = result.scalars().all()

        if not tokens:
            raise ValueError(
                "No email integration connected. "
                "Run `daily connect gmail` or `daily connect outlook` first."
            )

        # Pick the most recently updated token; prefer microsoft if both exist
        microsoft_token = next((t for t in tokens if t.provider == "microsoft"), None)
        google_token = next((t for t in tokens if t.provider == "google"), None)
        token = microsoft_token or google_token

        granted_scopes = set(token.scopes.split()) if token.scopes else set()
        access_token = decrypt_token(token.encrypted_access_token, vault_key)

        # Populate known_addresses from recent email metadata
        known_addresses: set[str] = set()
        try:
            from datetime import datetime, timedelta

            from daily.orchestrator.session import get_email_adapters

            adapters = get_email_adapters()
            if adapters:
                since = datetime.now() - timedelta(days=90)
                page = await adapters[0].list_emails(since=since)
                known_addresses = {_extract_email(e.sender) for e in page.emails if e.sender}
                known_addresses.update(_extract_email(e.recipient) for e in page.emails if e.recipient)
        except Exception as exc:
            logger.warning("_build_executor_for_type: could not load known_addresses: %s", exc)

        if token.provider == "microsoft":
            from msgraph import GraphServiceClient

            class _StaticToken:
                def __init__(self, tok: str) -> None:
                    self._tok = tok

                def get_token(self, *scopes: str, **kwargs: object) -> object:
                    import time

                    from azure.core.credentials import AccessToken

                    return AccessToken(self._tok, int(time.time()) + 3600)

            graph_client = GraphServiceClient(credentials=_StaticToken(access_token))
            return OutlookExecutor(
                graph_client=graph_client,
                known_addresses=known_addresses,
                granted_scopes=granted_scopes,
            )
        else:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build

            refresh_token = (
                decrypt_token(token.encrypted_refresh_token, vault_key)
                if token.encrypted_refresh_token else None
            )
            creds = Credentials(
                token=access_token,
                refresh_token=refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=settings.google_client_id,
                client_secret=settings.google_client_secret,
            )
            service = build("gmail", "v1", credentials=creds)
            return GmailExecutor(
                service=service,
                known_addresses=known_addresses,
                granted_scopes=granted_scopes,
            )

    elif action_type == ActionType.draft_message:
        async with async_session() as session:
            stmt = select(IntegrationToken).where(
                IntegrationToken.user_id == user_id,
                IntegrationToken.provider == "slack",
            )
            result = await session.execute(stmt)
            token = result.scalar_one_or_none()

        if not token:
            raise ValueError(
                "No Slack integration connected. Run `daily connect slack` first."
            )

        granted_scopes = set(token.scopes.split()) if token.scopes else set()
        bot_token = decrypt_token(token.encrypted_access_token, vault_key)

        from slack_sdk import WebClient

        client = WebClient(token=bot_token)
        return SlackExecutor(
            client=client,
            known_channels=set(),  # Channel IDs validated separately in M2
            granted_scopes=granted_scopes,
        )

    elif action_type in (ActionType.schedule_event, ActionType.reschedule_event):
        async with async_session() as session:
            stmt = select(IntegrationToken).where(
                IntegrationToken.user_id == user_id,
                IntegrationToken.provider == "google",
            )
            result = await session.execute(stmt)
            token = result.scalar_one_or_none()

        if not token:
            raise ValueError(
                "No Google Calendar integration connected. "
                "Run `daily connect gmail` first (Google Calendar uses the same OAuth grant)."
            )

        granted_scopes = set(token.scopes.split()) if token.scopes else set()
        access_token = decrypt_token(token.encrypted_access_token, vault_key)
        refresh_token = (
            decrypt_token(token.encrypted_refresh_token, vault_key)
            if token.encrypted_refresh_token else None
        )

        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
        )
        service = build("calendar", "v3", credentials=creds)

        return GoogleCalendarExecutor(
            service=service,
            known_addresses=set(),  # Calendar attendees validated from contacts in M2
            granted_scopes=granted_scopes,
        )

    else:
        raise ValueError(f"Unsupported action_type for executor dispatch: {action_type}")


async def execute_node(state: SessionState) -> dict:
    """Execute or cancel an action based on approval_decision.

    Dispatches to the correct ActionExecutor based on action_type and provider.
    Calls executor.validate() (ACT-06 + D-11 scope check) before execute().
    Logs the outcome via asyncio.create_task (fire-and-forget, D-08).

    Decision values:
      'confirm' — build executor, validate, execute, log
      anything else — treat as rejection, log and return cancellation message

    Security boundaries:
      T-04-16: execute_node is only reachable via approval_node in the graph.
      T-04-17: executor.validate() checks write scopes before any API call (D-11).

    Args:
        state: Current SessionState with approval_decision and pending_action set.

    Returns:
        State update dict with result message and cleared pending_action/approval_decision.
    """
    if state.approval_decision != "confirm":
        # Rejected — fire-and-forget log
        asyncio.create_task(_log_action(state, "rejected", None))
        return {
            "messages": [AIMessage(content="Action cancelled.")],
            "pending_action": None,
            "approval_decision": None,
        }

    # Confirmed — dispatch to executor
    try:
        executor = await _build_executor_for_type(
            state.pending_action.action_type,
            state.active_user_id,
        )
        # ACT-06 + D-11: validate() must pass before execute()
        await executor.validate(state.pending_action)
        result = await executor.execute(state.pending_action)

        outcome = "sent" if result.success else "failed"
        asyncio.create_task(_log_action(state, "approved", outcome))

        return {
            "messages": [AIMessage(content=f"Done. {result.summary}")],
            "pending_action": None,
            "approval_decision": None,
        }

    except ValueError as ve:
        # Validation failure — log as rejected, surface error to user
        asyncio.create_task(_log_action(state, "rejected", "validation_failed"))
        return {
            "messages": [AIMessage(content=f"Cannot execute: {ve}")],
            "pending_action": None,
            "approval_decision": None,
        }
    except Exception as exc:
        logger.warning("execute_node: unexpected error: %s", exc)
        asyncio.create_task(_log_action(state, "approved", "failed"))
        return {
            "messages": [AIMessage(content=f"Action failed: {exc}")],
            "pending_action": None,
            "approval_decision": None,
        }


async def memory_node(state: SessionState) -> dict:
    """Handle memory transparency commands: query, delete, clear, disable.

    Sub-intent dispatch via keyword matching on last user message.
    Priority: clear > delete > query > disable (per Research Pitfall 1 — "forget
    everything" must not route to single-fact delete).
    All operations bypass the memory_enabled gate — transparency always works (D-02/D-06).
    No approval gate — D-06: direct DB execution with verbal confirmation.

    Creates its own DB session (established node pattern via async_session()).

    Args:
        state: Current SessionState with messages and active_user_id.

    Returns:
        State update dict with AIMessage containing verbal confirmation.
    """
    from daily.db.engine import async_session  # noqa: PLC0415

    user_id = state.active_user_id
    last_msg = state.messages[-1].content.lower() if state.messages else ""

    try:
        # Sub-intent keyword sets (must match graph.py D-01 keywords)
        memory_query_keywords = ["what do you know", "what do you remember",
                                 "tell me what you know", "what have you learned"]
        memory_clear_keywords = ["forget everything", "clear my memory", "reset my memory"]
        memory_delete_keywords = ["forget that", "delete that", "remove that fact"]
        memory_disable_keywords = ["disable memory", "stop learning",
                                   "turn off memory", "don't remember"]

        async with async_session() as db_session:
            # CRITICAL: check clear BEFORE delete — "forget everything" must not route
            # to single-fact delete (Research Pitfall 1)
            if any(kw in last_msg for kw in memory_clear_keywords):
                count = await clear_all_memories(user_id, db_session)
                if count == 0:
                    narrative = "I don't have any memories stored about you."
                else:
                    narrative = f"Done, I've cleared all {count} things I knew about you."

            elif any(kw in last_msg for kw in memory_delete_keywords):
                # Extract the description from the message — strip the keyword prefix
                # to get the user's fact description for cosine matching
                raw_description = last_msg
                for kw in memory_delete_keywords:
                    raw_description = raw_description.replace(kw, "").strip()
                if not raw_description:
                    raw_description = last_msg  # fall back to full message if stripping empties it

                deleted_fact = await delete_memory_fact(user_id, raw_description, db_session)
                if deleted_fact is None:
                    narrative = "I couldn't find a matching memory to delete."
                else:
                    narrative = "Done, I've forgotten that."

            elif any(kw in last_msg for kw in memory_query_keywords):
                facts = await list_all_memories(user_id, db_session, limit=10)
                if not facts:
                    narrative = "I don't know anything about you yet."
                else:
                    items = " ".join(f"{i + 1}. {fact}." for i, fact in enumerate(facts))
                    narrative = f"Here's what I know about you. {items}"

            elif any(kw in last_msg for kw in memory_disable_keywords):
                await upsert_preference(user_id, "memory_enabled", "false", db_session)
                narrative = (
                    "Memory learning disabled. I'll stop extracting new facts. "
                    "Your existing memories are preserved until you delete them."
                )

            else:
                narrative = (
                    "I'm not sure what memory operation you meant. "
                    "Try asking 'what do you know about me?'"
                )

    except Exception as exc:
        logger.warning("memory_node: unexpected failure: %s", exc)
        narrative = "I couldn't complete that right now."

    return {"messages": [AIMessage(content=narrative)]}


async def _log_action(
    state: SessionState,
    status: str,
    outcome: str | None,
) -> None:
    """Fire-and-forget action audit log. Creates its own DB session.

    Mirrors _capture_signal pattern — called via asyncio.create_task() so
    it never blocks the voice response path (D-08).

    Args:
        state: Current SessionState with pending_action set.
        status: Approval status string ('approved' or 'rejected').
        outcome: Outcome string ('sent', 'failed') or None.
    """
    try:
        from daily.actions.log import append_action_log
        from daily.db.engine import async_session

        action = state.pending_action
        target = (
            action.recipient
            or action.channel_id
            or action.event_id
            or ""
        )
        async with async_session() as session:
            await append_action_log(
                user_id=state.active_user_id,
                action_type=action.action_type.value,
                target=target,
                content_summary=action.body,
                full_body=action.body,
                approval_status=status,
                outcome=outcome,
                session=session,
            )
    except Exception as exc:
        logger.warning("_log_action: failed to write action log: %s", exc)
