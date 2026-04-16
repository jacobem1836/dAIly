"""
Briefing pipeline orchestrator — end-to-end briefing generation.

Connects: ingest -> rank -> fetch bodies -> redact -> narrate -> cache.

Key contracts enforced here:
  D-02: List metadata -> rank -> fetch bodies for top-N only (done in context_builder).
  D-09/D-10: Redact per-item before narrator.
  D-11/SEC-05: Narrator receives only pre-summarised metadata — no raw bodies.
  D-14: Cache in Redis with 24h TTL.
  D-15: Cache miss triggers on-demand synchronous generation.
  SEC-02: raw_bodies flow from context_builder -> redactor in-memory only,
          cleared after redaction, never written to cache or DB.
  T-02-11: Only the redacted narrative is cached in Redis.

All pipeline parameters are provided by _build_pipeline_kwargs() in scheduler.py
when called from the cron job, or passed directly for on-demand generation.
"""

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from openai import AsyncOpenAI
from redis.asyncio import Redis

from daily.briefing.cache import cache_briefing, get_briefing
from daily.briefing.context_builder import build_context
from daily.briefing.models import BriefingOutput
from daily.briefing.narrator import generate_narrative
from daily.briefing.redactor import redact_emails, redact_messages
from daily.integrations.base import CalendarAdapter, EmailAdapter, MessageAdapter
from daily.profile.models import UserPreferences

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def run_briefing_pipeline(
    user_id: int,
    email_adapters: list[EmailAdapter],
    calendar_adapters: list[CalendarAdapter],
    message_adapters: list[MessageAdapter],
    vip_senders: frozenset[str],
    user_email: str,
    top_n: int,
    redis: Redis,
    openai_client: AsyncOpenAI,
    preferences: UserPreferences | None = None,
    db_session: "AsyncSession | None" = None,
) -> BriefingOutput:
    """Full pipeline: ingest -> rank -> fetch bodies -> redact -> narrate -> cache.

    Per D-02: list metadata -> rank -> fetch bodies for top-N only.
    Per D-09/D-10: redact per-item before narrator.
    Per D-11/SEC-05: narrator returns {"narrative": "..."} -- intent only.
    Per D-14: cache in Redis with 24h TTL.
    SEC-02: raw_bodies flow from context_builder -> redactor in-memory only.
            raw_bodies are cleared after redaction -- never cached or logged.

    All parameters are provided by _build_pipeline_kwargs() in scheduler.py
    when called from the cron job, or directly when called from
    get_or_generate_briefing() for on-demand generation.

    Args:
        user_id: User ID for context assembly and cache key.
        email_adapters: List of email adapter instances.
        calendar_adapters: List of calendar adapter instances.
        message_adapters: List of message adapter instances.
        vip_senders: Set of VIP sender email addresses for priority override.
        user_email: User's primary email address for recipient scoring.
        top_n: Max number of emails to include in the briefing.
        redis: Async Redis connection for caching the output.
        openai_client: Async OpenAI client for redaction and narration.
        preferences: Optional user preferences for tone/length/order. If None,
                     narrator uses defaults.
        db_session: Optional AsyncSession for adaptive ranking. When provided,
                    per-sender multipliers are fetched and applied to email
                    ranking. When None, adaptive ranking is skipped and pure
                    heuristics are used — the briefing always delivers regardless
                    (graceful-degradation contract).

    Returns:
        BriefingOutput with narrative, generated_at, and version.
    """
    logger.info("Starting briefing pipeline for user %d", user_id)

    # Step 1: Build context (ingest + rank + fetch bodies for top-N)
    # build_context populates context.raw_bodies with fetched email/Slack bodies.
    context = await build_context(
        user_id=user_id,
        email_adapters=email_adapters,
        calendar_adapters=calendar_adapters,
        message_adapters=message_adapters,
        vip_senders=vip_senders,
        user_email=user_email,
        top_n=top_n,
        db_session=db_session,
    )

    # Step 2: Redact -- summarise + credential strip per-item (SEC-02)
    # Extract raw bodies from context.raw_bodies by message_id for each source.
    # This is the key SEC-02 handoff: raw bodies travel in-memory from
    # context_builder -> redactor -> summaries. After redaction, raw_bodies
    # are no longer needed.

    if context.emails:
        # Extract email raw bodies from context.raw_bodies by message_id
        email_bodies = {
            email.metadata.message_id: context.raw_bodies.get(
                email.metadata.message_id, ""
            )
            for email in context.emails
        }
        context.emails = await redact_emails(
            context.emails, email_bodies, openai_client
        )

    if context.slack.messages:
        # Extract Slack raw texts from context.raw_bodies by message_id
        slack_texts = {
            msg.message_id: context.raw_bodies.get(msg.message_id, "")
            for msg in context.slack.messages
        }
        context.slack.summaries = await redact_messages(
            context.slack.messages, slack_texts, openai_client
        )

    # Clear raw_bodies after redaction -- no longer needed in memory (T-02-11)
    context.raw_bodies.clear()

    # Step 3: Generate narrative (BRIEF-06)
    # Narrator receives only pre-summarised metadata -- no raw bodies (D-11/SEC-05)
    output = await generate_narrative(context, openai_client, preferences=preferences)

    # Step 4: Cache in Redis (BRIEF-01, D-14)
    await cache_briefing(redis, user_id, output)

    logger.info("Briefing pipeline complete for user %d, cached", user_id)
    return output


async def get_or_generate_briefing(
    user_id: int,
    redis: Redis,
    generate_kwargs: dict,
) -> BriefingOutput:
    """Get cached briefing or generate on-demand (per D-15).

    Cache miss triggers synchronous generation -- never returns 'not ready'.
    This ensures BRIEF-01: the briefing always delivers.

    Cache hit serves in under 0.1s from Redis (BRIEF-01 latency requirement).

    Args:
        user_id: User ID for cache lookup and pipeline execution.
        redis: Async Redis connection.
        generate_kwargs: Dict containing all params for run_briefing_pipeline
            except user_id and redis (which are passed directly).
            Keys: email_adapters, calendar_adapters, message_adapters,
                  vip_senders, user_email, top_n, openai_client.

    Returns:
        BriefingOutput from cache (fast path) or freshly generated (slow path).
    """
    today = datetime.now(tz=timezone.utc).date()
    cached = await get_briefing(redis, user_id, today)
    if cached is not None:
        return cached

    # Cache miss -- generate on demand (D-15)
    logger.info("Cache miss for user %d on %s, generating on-demand", user_id, today)
    return await run_briefing_pipeline(user_id=user_id, redis=redis, **generate_kwargs)
