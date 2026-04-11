"""Orchestrator graph node functions.

respond_node: GPT-4.1 mini — quick conversational follow-ups (D-02).
summarise_thread_node: GPT-4.1 — reasoning-heavy thread summarisation (D-02, BRIEF-07).
draft_node: Stub for Plan 01 — full LLM drafting in Plan 02.
approval_node: Human-in-the-loop interrupt gate using langgraph.types.interrupt (T-04-02).
execute_node: Executes approved action (stub in Plan 01) and fire-and-forget logs.

Security boundaries enforced in this module:
  SEC-05: response_format=json_object, no tools= parameter, OrchestratorIntent validation
  SEC-02/SEC-04: raw email bodies pass through summarise_and_redact() before any state write
  T-03-06: No tools= on any LLM call — prevents privilege escalation
  T-03-07: raw_body is a local variable only, never assigned to state fields
  T-04-02: No direct edge START -> execute; approval_node interrupt() fires before any execution

Signal/action capture:
  D-08: append_signal / append_action_log wrapped in asyncio.create_task() — fire-and-forget.
"""

import asyncio
import logging

from langchain_core.messages import AIMessage
from langgraph.types import interrupt
from openai import AsyncOpenAI

from daily.briefing.redactor import summarise_and_redact
from daily.orchestrator.models import OrchestratorIntent
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
    from daily.orchestrator.session import get_email_adapters

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


async def draft_node(state: SessionState) -> dict:
    """Stub draft node for Plan 01.

    Full LLM drafting logic (reading context, generating body, setting pending_action)
    is implemented in Plan 02. For Plan 01 this node is a pass-through — pending_action
    is expected to already be set in state (e.g. injected by tests or future intent node).

    If pending_action is None, returns a guidance message and does not proceed to approval.

    Args:
        state: Current SessionState, expected to have pending_action set.

    Returns:
        Empty dict (no state change) when pending_action is set, or a message dict when not.
    """
    if state.pending_action is None:
        return {"messages": [AIMessage(content="No action to draft.")]}
    # pending_action already set — pass through to approval
    return {}


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
