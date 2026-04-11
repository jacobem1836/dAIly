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
from datetime import datetime, timedelta

from langchain_core.messages import AIMessage
from langgraph.types import interrupt
from openai import AsyncOpenAI

from daily.actions.base import ActionDraft, ActionType
from daily.briefing.redactor import summarise_and_redact
from daily.orchestrator.models import OrchestratorIntent
from daily.orchestrator.session import get_email_adapters
from daily.orchestrator.state import SessionState
from daily.profile.signals import SignalType

logger = logging.getLogger(__name__)

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
    "USER PREFERENCES: tone={tone}\n"
    "USER INSTRUCTION: {instruction}\n\n"
    "BRIEFING CONTEXT (for reference):\n{briefing_narrative}\n\n"
    "Output MUST be valid JSON with these fields:\n"
    '{{"recipient": "email@example.com or null", "subject": "Re: ... or null", '
    '"body": "the full draft text", "event_title": "null or title", '
    '"start_dt": "null or ISO datetime", "end_dt": "null or ISO datetime", '
    '"attendees": []}}'
)

# Maximum number of sent emails to use as style examples (D-06)
_MAX_STYLE_EXAMPLES = 5


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

    system_content = RESPOND_SYSTEM_PROMPT.format(
        briefing_narrative=state.briefing_narrative or "(no briefing loaded)",
        tone=state.preferences.get("tone", "conversational"),
        length=state.preferences.get("briefing_length", "standard"),
    )

    client = AsyncOpenAI()
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

    return {"messages": [AIMessage(content=narrative)]}


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

    # Extract target reference from last user message
    last_content = state.messages[-1].content if state.messages else ""
    # Use a placeholder message_id — real extraction depends on briefing context
    # In Phase 3 this is a best-effort lookup; Phase 5 will wire full context
    message_id = last_content  # pass through so adapter can match by subject/id

    client = AsyncOpenAI()

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
        # Fetch sent emails — adapter list_emails accepts since and a sent filter
        sent_emails = await adapters[0].list_emails(
            since=since,
            label_filter="SENT",
        )
        # Limit to _MAX_STYLE_EXAMPLES to avoid bloating the prompt
        sent_emails = sent_emails[:_MAX_STYLE_EXAMPLES]

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
    # Extract instruction from last human message
    instruction = state.messages[-1].content if state.messages else "draft an email"

    # Infer action type from instruction keywords
    action_type = _infer_action_type(instruction)

    tone = state.preferences.get("tone", "conversational")
    briefing_narrative = state.briefing_narrative or "(no briefing loaded)"

    client = AsyncOpenAI()

    # Fetch style examples (T-04-07: all bodies redacted before prompt inclusion)
    style_examples = await _fetch_style_examples(client)

    # Build system prompt
    system_content = DRAFT_SYSTEM_PROMPT.format(
        action_type=action_type.value.replace("_", " "),
        style_examples=style_examples or "(no style examples available)",
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
            event_title=parsed.get("event_title") or None,
            start_dt=start_dt,
            end_dt=end_dt,
            attendees=attendees,
        )

        action_label = action_type.value.replace("_", " ")
        return {
            "pending_action": draft,
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

    CRITICAL: interrupt() must NOT be wrapped in try/except. LangGraph uses
    a special exception mechanism internally — catching it would break the
    human-in-the-loop pattern entirely.

    Builds a preview payload from pending_action and calls interrupt() to
    pause graph execution. The user's decision string is returned via
    Command(resume=...) and stored as approval_decision.

    Args:
        state: Current SessionState with pending_action set.

    Returns:
        State update dict with approval_decision set to the user's decision string.
    """
    payload = {
        "preview": state.pending_action.card_text(),
        "action_type": state.pending_action.action_type.value,
    }
    decision = interrupt(payload)
    return {"approval_decision": decision}


async def execute_node(state: SessionState) -> dict:
    """Execute or cancel an action based on approval_decision.

    Logs the outcome via asyncio.create_task (fire-and-forget, D-08).
    Actual executor dispatch (GmailSendExecutor etc.) is wired in Plan 03.

    Decision values:
      'confirm' — execute the action (stub: return success message)
      anything else — treat as rejection, return cancellation message

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

    # Confirmed — stub execution (Plan 03 will dispatch to real executors)
    asyncio.create_task(_log_action(state, "approved", "sent"))
    return {
        "messages": [AIMessage(content="Done. Action executed successfully.")],
        "pending_action": None,
        "approval_decision": None,
    }


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
