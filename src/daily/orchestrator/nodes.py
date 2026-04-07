"""Orchestrator graph node functions.

respond_node: GPT-4.1 mini — quick conversational follow-ups (D-02).
summarise_thread_node: GPT-4.1 — reasoning-heavy thread summarisation (D-02, BRIEF-07).

Security boundaries enforced in this module:
  SEC-05: response_format=json_object, no tools= parameter, OrchestratorIntent validation
  SEC-02/SEC-04: raw email bodies pass through summarise_and_redact() before any state write
  T-03-06: No tools= on any LLM call — prevents privilege escalation
  T-03-07: raw_body is a local variable only, never assigned to state fields

Signal capture:
  D-08: append_signal wrapped in asyncio.create_task() — fire-and-forget, does not
  block the voice response path.
"""

import asyncio
import logging

from langchain_core.messages import AIMessage
from openai import AsyncOpenAI

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
    from daily.briefing.redactor import summarise_and_redact
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
