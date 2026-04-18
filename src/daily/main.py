"""
FastAPI application entrypoint for dAIly.

The lifespan context manager wires the APScheduler briefing pipeline cron job:
  - On startup: parse briefing_schedule_time from Settings, then query BriefingConfig
    from the database to override with any user-persisted schedule. Falls back to the
    env/settings default if the DB is unreachable or no config row exists.
    Calls setup_scheduler, then scheduler.start(). Scheduler runs within the same
    asyncio event loop.
  - On shutdown: scheduler.shutdown(wait=False) to stop gracefully.

The default schedule is loaded from Settings.briefing_schedule_time (default "05:00" UTC).
If the user has saved a config via `daily config set briefing.schedule_time`, the value
is persisted to BriefingConfig in the database and takes effect on the next app restart.
"""

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Response
from redis.asyncio import Redis as AsyncRedis
from sqlalchemy import func, select, text

from daily.briefing.scheduler import scheduler, setup_scheduler
from daily.config import Settings
from daily.db.engine import async_session
from daily.db.models import BriefingConfig, MemoryFact
from daily.logging_config import configure_logging
from daily.profile.signals import SignalLog

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan: start scheduler on boot, stop on shutdown."""
    settings = Settings()
    configure_logging(settings.log_level)

    # Parse briefing schedule time (format: "HH:MM")
    try:
        parts = settings.briefing_schedule_time.split(":")
        schedule_hour = int(parts[0])
        schedule_minute = int(parts[1])
    except (IndexError, ValueError):
        logger.warning(
            "Invalid briefing_schedule_time '%s', defaulting to 05:00",
            settings.briefing_schedule_time,
        )
        schedule_hour = 5
        schedule_minute = 0

    # Override with DB-stored schedule if available (BRIEF-02 persistence)
    try:
        async with async_session() as session:
            config = await session.execute(
                select(BriefingConfig).where(BriefingConfig.user_id == 1)
            )
            row = config.scalar_one_or_none()
            if row is not None:
                schedule_hour = row.schedule_hour
                schedule_minute = row.schedule_minute
                logger.info(
                    "Briefing schedule loaded from database: %02d:%02d UTC",
                    schedule_hour,
                    schedule_minute,
                )
    except Exception:
        logger.warning(
            "Failed to read BriefingConfig from database, using env default %02d:%02d",
            schedule_hour,
            schedule_minute,
        )

    # Register cron job for user_id=1 (M1 single-user)
    setup_scheduler(hour=schedule_hour, minute=schedule_minute, user_id=1)
    scheduler.start()
    logger.info(
        "Briefing scheduler started (cron: %02d:%02d UTC)",
        schedule_hour,
        schedule_minute,
    )

    yield

    scheduler.shutdown(wait=False)
    logger.info("Briefing scheduler stopped")


app = FastAPI(
    title="dAIly API",
    description="Voice-first AI personal assistant backend",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health(response: Response) -> dict:
    """Health check endpoint.

    Probes DB (SELECT 1), Redis (PING), and APScheduler (get_jobs).
    Returns 200 when all healthy, 503 when any dependency is degraded.

    Per D-05/D-06/D-07 (14-CONTEXT.md).
    T-14-04: Error messages from stdlib exceptions only — no credentials exposed.
    """
    settings = Settings()
    result: dict = {}
    degraded = False

    # Probe DB
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        result["db"] = "ok"
    except Exception as exc:
        result["db"] = f"error: {exc}"
        degraded = True

    # Probe Redis
    redis = AsyncRedis.from_url(settings.redis_url)
    try:
        await redis.ping()
        result["redis"] = "ok"
    except Exception as exc:
        result["redis"] = f"error: {exc}"
        degraded = True
    finally:
        await redis.aclose()

    # Check scheduler (APScheduler 3.x get_jobs() is synchronous)
    jobs = scheduler.get_jobs()
    if jobs:
        result["scheduler"] = "running"
    else:
        result["scheduler"] = "no_jobs"
        degraded = True

    result["status"] = "degraded" if degraded else "ok"

    if degraded:
        response.status_code = 503

    return result


@app.get("/metrics")
async def metrics() -> dict:
    """Operational metrics endpoint.

    Returns aggregate signal counts, memory entry count, and avg briefing latency.
    Per D-08 through D-12 (14-CONTEXT.md).

    T-14-03: Aggregate counts only — no PII. Acceptable for M1 single-host.
    T-14-05: At M1 scale (1 user), scan_iter matches 0-1 keys — acceptable.
    """
    settings = Settings()
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=7)

    # Signal counts (7-day rolling window) and memory entries
    signals_7d: dict = {}
    memory_entries: int = 0

    async with async_session() as session:
        # Signal counts per type in last 7 days (D-09, D-11)
        signal_result = await session.execute(
            select(SignalLog.signal_type, func.count(SignalLog.id))
            .where(SignalLog.created_at >= cutoff)
            .group_by(SignalLog.signal_type)
        )
        signals_7d = {row[0]: row[1] for row in signal_result.all()}

        # Memory fact count (D-09)
        memory_result = await session.execute(select(func.count(MemoryFact.id)))
        memory_entries = memory_result.scalar_one()

    # Briefing latency: scan Redis for per-user latency keys (D-10)
    # T-14-05: scan_iter at M1 scale matches 0-1 keys — acceptable
    latency_values: list[float] = []
    redis = AsyncRedis.from_url(settings.redis_url)
    try:
        async for key in redis.scan_iter("briefing:*:latency_s"):
            value = await redis.get(key)
            if value is not None:
                latency_values.append(float(value))
    finally:
        await redis.aclose()

    briefing_latency_avg_s = (
        sum(latency_values) / len(latency_values) if latency_values else 0.0
    )

    return {
        "briefing_latency_avg_s": briefing_latency_avg_s,
        "signals_7d": signals_7d,
        "memory_entries": memory_entries,
    }
