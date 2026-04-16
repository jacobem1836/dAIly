"""
APScheduler integration for briefing pipeline precompute (D-12/D-13).

Uses APScheduler 3.x AsyncIOScheduler (pinned 3.10.x in pyproject.toml).
The scheduler runs within the FastAPI process — no separate broker or worker.

Architecture:
  - `scheduler`: module-level AsyncIOScheduler instance, started by FastAPI lifespan.
  - `setup_scheduler(hour, minute, user_id)`: adds the cron job before start().
  - `update_schedule(hour, minute)`: reschedules the live job (D-13).
  - `_build_pipeline_kwargs(user_id, settings)`: resolves all pipeline dependencies
    (adapters from DB tokens, redis, openai_client, VIP list) — addresses the
    scheduler-to-pipeline parameter gap (HIGH review concern).
  - `_scheduled_pipeline_run(user_id)`: cron job entry point; calls
    _build_pipeline_kwargs then run_briefing_pipeline.

SEC-T-02-16: _build_pipeline_kwargs decrypts tokens in-memory only to instantiate
adapters. Tokens are never logged. OpenAI API key read from Settings (env var only).
"""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from openai import AsyncOpenAI
from redis.asyncio import Redis
from sqlalchemy import select

from daily.briefing.pipeline import run_briefing_pipeline
from daily.config import Settings
from daily.db.engine import async_session
from daily.db.models import IntegrationToken, VipSender
from daily.profile.service import load_profile

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")


async def _build_pipeline_kwargs(user_id: int, settings: Settings) -> dict:
    """Build all dependencies needed by run_briefing_pipeline.

    Addresses HIGH review concern: the cron job only receives user_id.
    This helper resolves adapters (from DB tokens), redis, openai_client,
    VIP list, and config so the pipeline function gets everything it needs.

    Imports concrete adapter classes inside the function to avoid circular
    imports and to keep the scheduler module testable with mocked adapters.

    SEC-T-02-16: Tokens decrypted in-memory only to instantiate adapters.
    The decrypted value is never logged or stored beyond local scope.

    Args:
        user_id: The user ID whose pipeline dependencies to resolve.
        settings: Application settings (contains redis_url, openai_api_key, etc).

    Returns:
        Dict suitable for: run_briefing_pipeline(user_id=user_id, **kwargs)
    """
    # Import concrete adapters here to avoid circular imports at module level
    from daily.integrations.google.adapter import GmailAdapter, GoogleCalendarAdapter
    from daily.integrations.microsoft.adapter import OutlookAdapter
    from daily.integrations.slack.adapter import SlackAdapter
    from daily.vault.crypto import decrypt_token
    import base64

    # Load VIP senders from DB
    async with async_session() as session:
        result = await session.execute(
            select(VipSender.email).where(VipSender.user_id == user_id)
        )
        vip_emails = frozenset(row[0] for row in result.fetchall())

    # Load integration tokens and instantiate adapters
    async with async_session() as session:
        result = await session.execute(
            select(IntegrationToken).where(IntegrationToken.user_id == user_id)
        )
        tokens = result.scalars().all()

    email_adapters = []
    calendar_adapters = []
    message_adapters = []
    user_email = ""

    vault_key = base64.b64decode(settings.vault_key) if settings.vault_key else b""

    for token in tokens:
        # Decrypt access token in-memory (SEC-T-02-16)
        decrypted = decrypt_token(token.encrypted_access_token, vault_key)
        provider = token.provider  # "google", "microsoft", "slack"

        if provider == "google":
            gmail = GmailAdapter(credentials=decrypted)
            email_adapters.append(gmail)
            cal = GoogleCalendarAdapter(credentials=decrypted)
            calendar_adapters.append(cal)
        elif provider == "microsoft":
            outlook = OutlookAdapter(credentials=decrypted)
            email_adapters.append(outlook)
        elif provider == "slack":
            slack = SlackAdapter(credentials=decrypted)
            message_adapters.append(slack)

    # Load user preferences for narrator (PERS-01)
    async with async_session() as session:
        preferences = await load_profile(user_id, session)

    # Create Redis and OpenAI clients
    redis = Redis.from_url(settings.redis_url)
    openai_client = AsyncOpenAI(api_key=settings.openai_api_key)

    return {
        "email_adapters": email_adapters,
        "calendar_adapters": calendar_adapters,
        "message_adapters": message_adapters,
        "vip_senders": vip_emails,
        "user_email": user_email,
        "top_n": settings.briefing_email_top_n,
        "redis": redis,
        "openai_client": openai_client,
        "preferences": preferences,
    }


async def _scheduled_pipeline_run(user_id: int) -> None:
    """Wrapper called by APScheduler cron job.

    Builds all pipeline dependencies via _build_pipeline_kwargs, then
    calls run_briefing_pipeline with a dedicated DB session. This is the
    bridge between the scheduler (which only knows user_id) and the pipeline
    (which needs everything).

    A fresh async session is opened per invocation — no session reuse across
    user boundaries (T-08-13). The async with block guarantees the session is
    closed (and rolled back on error) even if the pipeline raises (T-08-11).

    Redis connection created in _build_pipeline_kwargs is closed in finally
    to avoid connection leaks.
    """
    settings = Settings()
    kwargs: dict = {}
    try:
        kwargs = await _build_pipeline_kwargs(user_id, settings)
        async with async_session() as session:
            await run_briefing_pipeline(
                user_id=user_id,
                db_session=session,
                **kwargs,
            )
    except Exception:
        logger.exception("Scheduled briefing pipeline failed for user %d", user_id)
    finally:
        # Clean up redis connection created in _build_pipeline_kwargs
        redis = kwargs.get("redis")
        if redis is not None:
            await redis.aclose()


def setup_scheduler(hour: int, minute: int, user_id: int) -> None:
    """Add the briefing pipeline cron job. Called before scheduler.start().

    Uses _scheduled_pipeline_run as the job function (not run_briefing_pipeline
    directly) — the wrapper resolves all dependencies at runtime via
    _build_pipeline_kwargs.

    Args:
        hour: UTC hour for the cron schedule.
        minute: UTC minute for the cron schedule.
        user_id: User ID to pass to the pipeline job.
    """
    scheduler.add_job(
        _scheduled_pipeline_run,
        CronTrigger(hour=hour, minute=minute),
        id="briefing_precompute",
        replace_existing=True,
        args=[user_id],
    )


def update_schedule(hour: int, minute: int) -> None:
    """Reschedule the briefing precompute job (per D-13).

    Note: This only works when the FastAPI app is running (scheduler is active).
    CLI config changes persist to DB and take effect on next app startup.
    For live reschedule while app is running, call this function directly.

    Args:
        hour: New UTC hour for the cron schedule.
        minute: New UTC minute for the cron schedule.
    """
    scheduler.reschedule_job(
        "briefing_precompute",
        trigger=CronTrigger(hour=hour, minute=minute),
    )
