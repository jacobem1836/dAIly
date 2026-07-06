"""Per-user session bootstrap for the LiveKit agent worker.

Performs per-session setup for the LiveKit voice agent:
- resolve email adapters
- build graph with AsyncPostgresSaver
- create session config
- load initial state from Redis briefing cache + profile

Historical note: the local CLI voice pipeline (the legacy voice/loop.py module)
was the original reference implementation for this setup sequence. It was deleted in
Phase 21.45 (voice path consolidation). This module is the sole bootstrap path.

Audit H3: this module previously imported a private helper from daily.cli
(`_resolve_email_adapters`), which dragged Typer/input()/webbrowser (the
interactive CLI's dependencies) into the production LiveKit worker process
just to reuse one function. Adapter resolution now lives in the neutral
daily.integrations.resolve module, which both daily.cli and this module
import from — the worker no longer depends on the CLI at all.
"""
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from redis.asyncio import Redis

from daily.config import Settings
from daily.db.engine import async_session
from daily.integrations.resolve import resolve_email_adapters as _resolve_email_adapters
from daily.orchestrator.graph import build_graph
from daily.orchestrator.session import (
    create_session_config,
    initialize_session_state,
    set_email_adapters,
)

logger = logging.getLogger(__name__)


@dataclass
class SessionBundle:
    graph: object
    config: dict
    initial_state: dict
    briefing_narrative: str


@asynccontextmanager
async def load_user_session_state(
    user_id: int,
    settings: Settings | None = None,
) -> AsyncIterator[SessionBundle]:
    """Load graph + config + initial state for a user. Async context manager.

    Yields:
        SessionBundle with graph, config, initial_state, and briefing_narrative.
        briefing_narrative is "" when Redis cache is empty.

    On exit, AsyncPostgresSaver and Redis are closed automatically.
    """
    settings = settings or Settings()
    adapters = await _resolve_email_adapters(user_id, settings)
    set_email_adapters(adapters)

    # ponytail: audit M3 (deferred, lower priority) — this opens a fresh
    # psycopg connection pool AND re-runs checkpointer.setup() (schema
    # migration check) on every single LiveKit job dispatch / CLI chat
    # invocation, instead of once per worker process.
    #
    # Deferred rather than fixed in this pass: livekit-agents defaults to
    # JobExecutorType.PROCESS with idle-process reuse (WorkerOptions.
    # num_idle_processes), so genuinely sharing this pool across dispatches
    # means moving pool creation into WorkerOptions.prewarm_fnc and reading
    # it back from JobContext.proc.userdata in worker/agent.py — but
    # prewarm_fnc runs synchronously before any event loop exists, and an
    # asyncpg/psycopg pool created there would be bound to whatever loop is
    # active at that moment, not necessarily the one each job later runs
    # on (a classic cross-loop connection-pool bug). There's also no
    # existing test harness that mocks livekit-agents' proc lifecycle to
    # verify this safely. cli.py's own use of this same pattern is fine
    # as-is — one process, one chat session, no cross-session reuse to gain.
    #
    # Upgrade path: add a prewarm_fnc in worker/__main__.py that creates the
    # pool using the process's own loop (e.g. via asyncio.get_event_loop()
    # inside a loop.run_until_complete, matching livekit-agents' documented
    # prewarm pattern), store it on JobContext.proc.userdata, and have
    # load_user_session_state accept an optional pre-built checkpointer
    # instead of always constructing its own.
    async with AsyncPostgresSaver.from_conn_string(settings.database_url_psycopg) as checkpointer:
        await checkpointer.setup()
        graph = build_graph(checkpointer=checkpointer)
        config = await create_session_config(user_id)
        redis = Redis.from_url(settings.redis_url)
        try:
            async with async_session() as db_sess:
                initial_state = await initialize_session_state(user_id, redis, db_sess)
        finally:
            await redis.aclose()

        yield SessionBundle(
            graph=graph,
            config=config,
            initial_state=initial_state,
            briefing_narrative=initial_state.get("briefing_narrative", ""),
        )
