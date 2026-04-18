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

from fastapi import FastAPI
from sqlalchemy import select

from daily.briefing.scheduler import scheduler, setup_scheduler
from daily.config import Settings
from daily.db.engine import async_session
from daily.db.models import BriefingConfig
from daily.logging_config import configure_logging

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
async def health() -> dict:
    """Health check endpoint."""
    return {"status": "ok"}
