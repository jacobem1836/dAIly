"""Session entry point for the orchestrator graph.

Provides:
- Email adapter registry (set_email_adapters / get_email_adapters) for runtime
  injection of real EmailAdapter instances from the CLI chat command or FastAPI
  lifespan. Nodes use get_email_adapters() at call time — no module-level import.
- create_session_config: LangGraph thread_id scoped per user per day (T-03-04).
- initialize_session_state: Load cached briefing and user preferences into the
  initial state dict. Per D-11: reads from Redis cache only, does NOT re-run pipeline.
- run_session: Single-turn graph execution via ainvoke (not invoke — Pitfall 2).
- astream_session: Streaming variant for respond-intent turns using OpenAI SDK
  stream=True. Yields plain-text token deltas. Raises StreamingNotSupported for
  non-respond intents so the caller can fall back to run_session.
"""

import logging
import re
from collections.abc import AsyncIterator
from datetime import date, datetime, timedelta, timezone

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from daily.briefing.cache import get_briefing
from daily.profile.service import load_profile

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"[\w.+\-]+@[\w.\-]+")


def _extract_email(header_value: str) -> str:
    """Extract bare email address from an RFC 2822 From/To header value.

    Handles both "Name <email@example.com>" and bare "email@example.com" forms.
    Returns the first email address found, or the original string if none matches.
    """
    m = _EMAIL_RE.search(header_value)
    return m.group(0) if m else header_value

# ---------------------------------------------------------------------------
# Email adapter registry
# ---------------------------------------------------------------------------
# Module-level list injected at runtime by the CLI chat command or FastAPI
# lifespan before the first graph invocation. Graph nodes call get_email_adapters()
# at execution time — not import time — so late binding works correctly.

_email_adapters: list = []


def set_email_adapters(adapters: list) -> None:
    """Register email adapters for use by orchestrator nodes.

    Called by CLI chat command after resolving integration tokens into
    real GmailAdapter / OutlookAdapter instances.

    Args:
        adapters: List of EmailAdapter instances to register.
    """
    global _email_adapters
    _email_adapters = list(adapters)


def get_email_adapters() -> list:
    """Retrieve registered email adapters.

    Returns:
        Current list of registered EmailAdapter instances. Empty list if
        no adapters have been registered (summarise_thread_node handles this).
    """
    return _email_adapters


async def create_session_config(user_id: int, session_date: date | None = None) -> dict:
    """Create LangGraph config with scoped thread_id (T-03-04).

    Thread ID format: user-{user_id}-{date_iso}
    Scoping: one thread per user per calendar day. user_id is system-assigned
    (never user-supplied) so cross-user state access is prevented by design.

    Args:
        user_id: System-assigned user identifier.
        session_date: Date to scope the thread to. Defaults to today.

    Returns:
        LangGraph config dict with configurable.thread_id set.
    """
    d = session_date or date.today()
    return {"configurable": {"thread_id": f"user-{user_id}-{d.isoformat()}"}}


async def initialize_session_state(
    user_id: int,
    redis: Redis,
    db_session: AsyncSession,
    session_date: date | None = None,
) -> dict:
    """Load cached briefing and user preferences into initial state.

    Per D-11: reads from Redis cache only. Does NOT re-run the briefing
    pipeline (which lives in daily.briefing.scheduler and runs on cron).

    Args:
        user_id: User to load state for.
        redis: Async Redis connection for briefing cache lookup.
        db_session: Async SQLAlchemy session for profile lookup.
        session_date: Date of the briefing to load. Defaults to today.

    Returns:
        Dict with briefing_narrative, active_user_id, and preferences set.
        briefing_narrative is empty string on cache miss (no briefing pre-run today).
    """
    d = session_date or date.today()
    briefing = await get_briefing(redis, user_id, d)
    preferences = await load_profile(user_id, db_session)

    email_context: list[dict] = []
    adapters = get_email_adapters()
    if adapters:
        try:
            since = datetime.now(tz=timezone.utc) - timedelta(days=7)
            page = await adapters[0].list_emails(since=since)
            email_context = [
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
        except Exception:
            logger.warning("initialize_session_state: could not load email context")

    return {
        "briefing_narrative": briefing.narrative if briefing else "",
        "active_user_id": user_id,
        "preferences": preferences.model_dump(),
        "email_context": email_context,
    }


async def run_session(
    graph,
    user_input: str,
    config: dict,
    initial_state: dict | None = None,
):
    """Run a single turn through the orchestrator graph.

    Uses ainvoke (not invoke) to avoid hanging with async checkpointer (Pitfall 2).
    The checkpointer (MemorySaver or AsyncPostgresSaver) persists state between
    calls using the thread_id from config — session memory is automatic.

    Args:
        graph: Compiled LangGraph StateGraph.
        user_input: The user's text input for this turn.
        config: LangGraph config dict with configurable.thread_id.
        initial_state: Optional state dict merged into the first turn's input.
                      Pass on first turn only; subsequent turns use persisted state.

    Returns:
        Updated state dict from graph.ainvoke.
    """
    state_input: dict = {"messages": [("human", user_input)]}
    if initial_state:
        state_input.update(initial_state)
    return await graph.ainvoke(state_input, config)


# ---------------------------------------------------------------------------
# Streaming session — Plan 17-04 (Improvement 5)
# ---------------------------------------------------------------------------

class StreamingNotSupported(Exception):
    """Raised when the streaming path cannot handle the current intent.

    Callers should catch this and fall back to run_session.
    """


# Keywords that indicate a non-respond intent. Mirrors route_intent() in graph.py
# but kept here as a standalone copy to avoid circular imports. Keep in sync
# manually if route_intent keyword lists change.
_NON_RESPOND_KEYWORDS: tuple[str, ...] = (
    # Memory (Phase 10)
    "what do you know", "what do you remember", "tell me what you know",
    "what have you learned", "forget everything", "clear my memory",
    "reset my memory", "forget that", "delete that", "remove that fact",
    "disable memory", "stop learning", "turn off memory", "don't remember",
    # Resume briefing
    "continue my briefing", "resume briefing", "go back to the briefing",
    "continue briefing", "pick up the briefing", "where were we",
    # Skip / re-request (Phase 13)
    "skip", "next", "move on", "next item", "skip this",
    "repeat that", "say that again", "what was that", "repeat",
    "say again", "come again", "pardon",
    # Summarise
    "summarise", "summarize", "summary", "thread", "email chain",
    # Draft / action
    "draft", "reply", "send", "compose", "write", "schedule",
    "reschedule", "book", "move", "create event", "cancel meeting",
    # Exit / quit / approval (handled in loop.py before astream_session is called,
    # but guard here defensively)
    "exit", "quit", "yes", "no", "approve", "confirm",
)


def _looks_like_respond_intent(user_input: str) -> bool:
    """Return True when user_input appears to be a plain respond-intent turn.

    Uses a denylist approach: if any non-respond keyword appears in the
    normalised input, returns False (caller should use run_session instead).

    Args:
        user_input: Raw utterance text from the user.

    Returns:
        True if the input should be handled by the streaming respond path.
    """
    normalized = user_input.strip().lower()
    return not any(kw in normalized for kw in _NON_RESPOND_KEYWORDS)


async def astream_session(
    graph,
    user_input: str,
    config: dict,
    initial_state: dict | None = None,
) -> AsyncIterator[str]:
    """Yield plain-text token deltas for respond-intent turns.

    Uses the OpenAI SDK stream=True path (not LangGraph .astream_events())
    because respond_node uses response_format=json_object which blocks LangGraph
    from intercepting token-level events (RESEARCH Improvement 5, Option A).

    For non-respond intents (summarise, draft, approval flows, exit/quit, etc.)
    this raises StreamingNotSupported so the caller can fall back to run_session.

    Args:
        graph: Compiled LangGraph StateGraph (unused for respond turns but kept
               for API symmetry with run_session).
        user_input: The user's text input for this turn.
        config: LangGraph config dict (unused for respond turns; included for
                API symmetry with run_session).
        initial_state: Optional state dict (same semantics as run_session —
                       checked but not forwarded since streaming bypasses the graph).

    Yields:
        Plain-text token delta strings from the OpenAI streaming response.

    Raises:
        StreamingNotSupported: When the intent is not a plain respond turn.
    """
    if not _looks_like_respond_intent(user_input):
        raise StreamingNotSupported(f"non-respond intent: {user_input!r}")

    # Build the OpenAI client the same way nodes.py does.
    from daily.config import Settings  # noqa: PLC0415
    from openai import AsyncOpenAI  # noqa: PLC0415

    client = AsyncOpenAI(api_key=Settings().openai_api_key)

    # Mirror respond_node's system prompt but drop response_format=json_object
    # and request plain narrative text instead.
    briefing_narrative = "(no briefing loaded)"
    tone = "conversational"
    length = "standard"
    if initial_state:
        briefing_narrative = initial_state.get("briefing_narrative") or briefing_narrative
        prefs = initial_state.get("preferences") or {}
        tone = prefs.get("tone", tone)
        length = prefs.get("briefing_length", length)

    system_prompt = (
        "You are a personal briefing assistant. The user is asking about their morning briefing.\n"
        "Answer based on the briefing context provided. Be concise and conversational.\n\n"
        f"BRIEFING CONTEXT:\n{briefing_narrative}\n\n"
        f"USER PREFERENCES: tone={tone}, length={length}\n\n"
        "Respond with plain narrative text only — no JSON wrapping, no code blocks."
    )

    stream = await client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ],
        stream=True,
        max_tokens=400,
    )

    async for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta
