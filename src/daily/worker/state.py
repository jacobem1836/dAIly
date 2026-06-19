"""Per-user session bootstrap for the LiveKit agent worker.

Performs per-session setup for the LiveKit voice agent:
- resolve email adapters
- build graph with AsyncPostgresSaver
- create session config
- load initial state from Redis briefing cache + profile

Historical note: the local CLI voice pipeline (the legacy voice/loop.py module)
was the original reference implementation for this setup sequence. It was deleted in
Phase 21.45 (voice path consolidation). This module is the sole bootstrap path.
"""
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from redis.asyncio import Redis

from daily.cli import _resolve_email_adapters
from daily.config import Settings
from daily.db.engine import async_session
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
