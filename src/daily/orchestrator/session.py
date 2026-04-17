"""Session entry point for the orchestrator graph.

Provides:
- Email adapter registry (set_email_adapters / get_email_adapters) for runtime
  injection of real EmailAdapter instances from the CLI chat command or FastAPI
  lifespan. Nodes use get_email_adapters() at call time — no module-level import.
- create_session_config: LangGraph thread_id scoped per user per day (T-03-04).
- initialize_session_state: Load cached briefing and user preferences into the
  initial state dict. Per D-11: reads from Redis cache only, does NOT re-run pipeline.
- run_session: Single-turn graph execution via ainvoke (not invoke — Pitfall 2).
"""

import logging
import re
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

    # Phase 9 INTEL-02: retrieve cross-session memories for live-session injection.
    # Hard-gated on memory_enabled — retrieve_relevant_memories returns [] when False.
    user_memories: list[str] = []
    if preferences.memory_enabled:
        from daily.profile.memory import retrieve_relevant_memories  # noqa: PLC0415
        user_memories = await retrieve_relevant_memories(
            user_id=user_id,
            query_text="today's briefing context",
            db_session=db_session,
            top_k=10,
        )

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
        "user_memories": user_memories,
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
