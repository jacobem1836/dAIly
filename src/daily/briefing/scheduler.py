"""
APScheduler integration for briefing pipeline precompute (D-12/D-13).

Uses APScheduler 3.x AsyncIOScheduler (pinned 3.10.x in pyproject.toml).
The scheduler runs within the FastAPI process — no separate broker or worker.

Architecture:
  - `scheduler`: module-level AsyncIOScheduler instance, started by FastAPI lifespan.
  - `setup_scheduler(hour, minute, user_id)`: adds the cron job before start().
  - `setup_scheduler_for_user(hour, minute, user_id, timezone)`: adds/replaces the
    per-user cron job. `timezone` is passed straight to APScheduler's CronTrigger
    so hour/minute are interpreted as LOCAL wall-clock time in that zone — DST
    transitions are then handled by CronTrigger itself instead of going stale
    (audit M1 fix; see BriefingConfig.timezone / users/router.py).
  - `update_schedule(hour, minute)`: reschedules the live job (D-13).
  - `_build_pipeline_kwargs(user_id, settings)`: resolves all pipeline dependencies
    (adapters from DB tokens, redis, openai_client, VIP list, per-user BriefingConfig
    overrides) — addresses the scheduler-to-pipeline parameter gap (HIGH review
    concern) and the write-only BriefingConfig.email_top_n / slack_channels fields
    (audit C1).
  - `_scheduled_pipeline_run(user_id)`: cron job entry point; calls
    _build_pipeline_kwargs then run_briefing_pipeline. Guarded by a
    Redis-backed distributed lock (audit M2) so that if the API scales to
    multiple replicas, only one replica actually runs a given user's
    pipeline per day — the others skip, avoiding duplicate OpenAI spend.
  - `setup_token_refresh_job()` / `_run_token_refresh_job()`: periodic job that
    proactively refreshes expiring Google/Microsoft OAuth tokens (audit C2) —
    without this, Outlook/Graph calls 401 forever once the access token expires,
    since _StaticTokenCredential never re-derives a token on its own.

SEC-T-02-16: _build_pipeline_kwargs decrypts tokens in-memory only to instantiate
adapters. Tokens are never logged. OpenAI API key read from Settings (env var only).
"""

import logging
import secrets

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from openai import AsyncOpenAI
from redis.asyncio import Redis
from sqlalchemy import select

from daily.briefing.pipeline import run_briefing_pipeline
from daily.config import Settings
from daily.db.engine import async_session
from daily.db.models import BriefingConfig, IntegrationToken, VipSender
from daily.profile.service import load_profile

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")

# How often the proactive token-refresh job runs (audit C2).
TOKEN_REFRESH_INTERVAL_MINUTES = 30

# TTL for the distributed run-lock (audit M2). Comfortably longer than a
# single briefing pipeline run should ever take, so a crashed holder doesn't
# permanently wedge the lock for the rest of the day.
BRIEFING_LOCK_TTL_SECONDS = 30 * 60


async def _try_acquire_run_lock(lock_key: str, ttl_seconds: int, settings: Settings) -> bool:
    """Attempt to acquire a short-lived distributed lock via Redis SET NX EX.

    Audit M2: if the API scales to >1 replica, every replica's APScheduler
    would otherwise fire the same cron job at the same time, duplicating
    OpenAI spend (and, for the token-refresh job, racing writes). Only the
    replica that wins the SET NX EX proceeds; others skip this run.

    Fails OPEN: if Redis is unreachable, this returns True (lock "acquired")
    so a single-replica deployment — or a transient Redis outage — never
    silently skips a scheduled briefing. The lock is a multi-replica
    optimization, not a correctness requirement for the common case.

    Args:
        lock_key: Redis key, e.g. "lock:briefing:{user_id}:{utc_date}".
        ttl_seconds: Lock TTL — must outlive the guarded work.
        settings: Application settings (for redis_url).

    Returns:
        True if this caller should proceed with the guarded work.
    """
    redis = Redis.from_url(settings.redis_url)
    try:
        token = secrets.token_hex(16)
        acquired = await redis.set(lock_key, token, nx=True, ex=ttl_seconds)
        return bool(acquired)
    except Exception:
        logger.warning(
            "Distributed lock unavailable for %s; proceeding without it", lock_key
        )
        return True
    finally:
        await redis.aclose()


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
    from daily.vault.crypto import decrypt_token, load_vault_key

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

    # Load per-user BriefingConfig overrides (audit C1: email_top_n and
    # slack_channels were persisted by cli.py/users.router but never read here
    # — the pipeline always fell back to the global settings default / an
    # empty channel list). Falls back to global defaults when no row exists.
    async with async_session() as session:
        result = await session.execute(
            select(BriefingConfig).where(BriefingConfig.user_id == user_id)
        )
        briefing_config = result.scalar_one_or_none()

    top_n = (
        briefing_config.email_top_n
        if briefing_config is not None
        else settings.briefing_email_top_n
    )
    slack_channels = (
        list(briefing_config.slack_channels)
        if briefing_config is not None and briefing_config.slack_channels
        else []
    )

    email_adapters = []
    calendar_adapters = []
    message_adapters = []
    user_email = ""

    vault_key = load_vault_key(settings.vault_key)

    for token in tokens:
        # Decrypt access token in-memory (SEC-T-02-16)
        decrypted = decrypt_token(token.encrypted_access_token, vault_key)
        provider = token.provider  # "google", "microsoft", "slack"

        if provider == "google":
            from google.oauth2.credentials import Credentials
            decrypted_refresh = (
                decrypt_token(token.encrypted_refresh_token, vault_key)
                if token.encrypted_refresh_token
                else None
            )
            google_creds = Credentials(
                token=decrypted,
                refresh_token=decrypted_refresh,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=settings.google_client_id,
                client_secret=settings.google_client_secret,
                scopes=token.scopes.split() if token.scopes else None,
            )
            gmail = GmailAdapter(credentials=google_creds)
            email_adapters.append(gmail)
            cal = GoogleCalendarAdapter(credentials=google_creds)
            calendar_adapters.append(cal)
        elif provider == "outlook":
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
        "top_n": top_n,
        "redis": redis,
        "openai_client": openai_client,
        "preferences": preferences,
        "slack_channels": slack_channels,
    }


async def _scheduled_pipeline_run(user_id: int) -> None:
    """Wrapper called by APScheduler cron job.

    Builds all pipeline dependencies via _build_pipeline_kwargs, then
    calls run_briefing_pipeline. This is the bridge between the scheduler
    (which only knows user_id) and the pipeline (which needs everything).

    Audit M2: guarded by a per-user, per-day distributed lock so that if
    the API scales to multiple replicas, only one actually runs the
    pipeline (avoiding duplicate OpenAI spend). See _try_acquire_run_lock.

    Redis connection created in _build_pipeline_kwargs is closed in finally
    to avoid connection leaks.
    """
    from datetime import datetime, timezone  # noqa: PLC0415

    settings = Settings()
    utc_date = datetime.now(timezone.utc).date().isoformat()
    lock_key = f"lock:briefing:{user_id}:{utc_date}"
    if not await _try_acquire_run_lock(lock_key, BRIEFING_LOCK_TTL_SECONDS, settings):
        logger.info(
            "Skipping scheduled briefing for user %d — lock held by another replica",
            user_id,
        )
        return

    kwargs: dict = {}
    try:
        kwargs = await _build_pipeline_kwargs(user_id, settings)
        await run_briefing_pipeline(user_id=user_id, **kwargs)
    except Exception:
        logger.exception("Scheduled briefing pipeline failed for user %d", user_id)
    finally:
        # Clean up redis connection created in _build_pipeline_kwargs
        redis = kwargs.get("redis")
        if redis is not None:
            await redis.aclose()


def setup_scheduler_for_user(
    hour: int, minute: int, user_id: int, timezone: str = "UTC"
) -> None:
    """Register a CronTrigger job for one user. Idempotent — replaces if exists.

    Audit M1 fix: `hour`/`minute` are interpreted as LOCAL wall-clock time in
    `timezone`, and that timezone string is passed straight to APScheduler's
    CronTrigger rather than hardcoding "UTC". CronTrigger re-resolves the
    local time against the zone on every fire, so DST transitions are handled
    automatically. Previously the caller (users/router.py) converted local
    time to a fixed UTC hour/minute at write time — correct on the day it was
    written, but silently wrong by an hour after the next DST transition,
    since a fixed UTC offset never actually captures a timezone's rules.

    Callers that only ever pass UTC values (e.g. the CLI's
    `briefing.schedule_time`, which is documented as UTC) are unaffected —
    `timezone="UTC"` behaves exactly as before.

    Args:
        hour: Local wall-clock hour for the cron schedule.
        minute: Local wall-clock minute for the cron schedule.
        user_id: User ID to pass to the pipeline job.
        timezone: IANA timezone string (e.g. "Australia/Brisbane") or "UTC".
    """
    job_id = f"briefing_user_{user_id}"
    scheduler.add_job(
        _scheduled_pipeline_run,
        trigger=CronTrigger(hour=hour, minute=minute, timezone=timezone),
        kwargs={"user_id": user_id},
        id=job_id,
        replace_existing=True,
    )


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


async def _run_token_refresh_job() -> None:
    """APScheduler job: proactively refresh expiring OAuth tokens (audit C2).

    Without this job, `daily.vault.refresh.refresh_expiring_tokens` was dead
    code — nothing called it — so once a Google or Microsoft access token
    expired, every subsequent API call 401'd forever with no repair path
    (Microsoft's OutlookAdapter._StaticTokenCredential in particular has no
    way to self-refresh; it always hands back the same access token).

    refresh_expiring_tokens already offloads its blocking provider HTTP calls
    to a worker thread internally (asyncio.to_thread — see vault/refresh.py),
    so this job never blocks the shared asyncio event loop.

    Failures for individual tokens are handled inside refresh_expiring_tokens
    (T-1-21) and never raise here; a failure to even load the vault key is
    caught so a bad/missing VAULT_KEY doesn't crash the scheduler thread.

    Audit M2: also guarded by the distributed lock. A double-run here is
    mostly harmless (each replica just re-derives/re-writes the same
    refreshed token), but the lock avoids two replicas racing a write to
    the same IntegrationToken row for the duration of one refresh tick.
    """
    from datetime import datetime, timezone  # noqa: PLC0415

    from daily.vault.crypto import load_vault_key
    from daily.vault.refresh import refresh_expiring_tokens

    settings = Settings()
    # Bucketed by interval so overlapping replica ticks share one lock key;
    # TTL is intentionally shorter than the interval so the lock always
    # clears well before the next legitimate run is due.
    tick_bucket = int(datetime.now(timezone.utc).timestamp() // (TOKEN_REFRESH_INTERVAL_MINUTES * 60))
    lock_key = f"lock:token_refresh:{tick_bucket}"
    lock_ttl = max(60, TOKEN_REFRESH_INTERVAL_MINUTES * 60 - 60)
    if not await _try_acquire_run_lock(lock_key, lock_ttl, settings):
        logger.info("Skipping token refresh job — lock held by another replica")
        return

    try:
        vault_key = load_vault_key(settings.vault_key)
    except Exception:
        logger.exception("Token refresh job: failed to load vault key, skipping run")
        return

    try:
        results = await refresh_expiring_tokens(async_session, vault_key)
    except Exception:
        logger.exception("Token refresh job failed unexpectedly")
        return

    failures = [r for r in results if not r["success"]]
    if results:
        logger.info(
            "Token refresh job: processed %d expiring token(s), %d failed",
            len(results),
            len(failures),
        )


def setup_token_refresh_job() -> None:
    """Register the periodic proactive token-refresh job (audit C2).

    Idempotent — replaces the existing job if called again. Call once at
    startup (see main.py lifespan), before scheduler.start().
    """
    scheduler.add_job(
        _run_token_refresh_job,
        trigger=IntervalTrigger(minutes=TOKEN_REFRESH_INTERVAL_MINUTES),
        id="token_refresh",
        replace_existing=True,
    )
