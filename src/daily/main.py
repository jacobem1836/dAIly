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
from fastapi.responses import JSONResponse
from sqlalchemy import select

from daily.auth.router import router as auth_router
from daily.briefing.router import router as briefing_router
from daily.briefing.scheduler import scheduler, setup_scheduler, setup_scheduler_for_user
from daily.config import Settings
from daily.db.engine import async_session
from daily.db.models import BriefingConfig
from daily.integrations.router import router as integrations_router
from daily.livekit.router import router as livekit_router
from daily.users.router import router as users_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan: start scheduler on boot, stop on shutdown.

    Registers one APScheduler cron job per BriefingConfig row (multi-user).
    If the DB is unreachable the scheduler starts with zero jobs rather than
    crashing the whole app (T-21-05-02 mitigation).
    """
    try:
        async with async_session() as session:
            result = await session.execute(select(BriefingConfig))
            rows = result.scalars().all()
        registered = 0
        for row in rows:
            setup_scheduler_for_user(
                hour=row.schedule_hour,
                minute=row.schedule_minute,
                user_id=row.user_id,
            )
            registered += 1
        logger.info("Registered %d per-user briefing cron jobs", registered)
    except Exception:
        logger.exception("Failed to load BriefingConfig rows; starting scheduler with no jobs")

    scheduler.start()
    logger.info("Briefing scheduler started")

    yield

    scheduler.shutdown(wait=False)
    logger.info("Briefing scheduler stopped")


app = FastAPI(
    title="dAIly API",
    description="Voice-first AI personal assistant backend",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(auth_router)
app.include_router(briefing_router)
app.include_router(integrations_router)
app.include_router(livekit_router)
app.include_router(users_router)


@app.get("/health")
async def health() -> dict:
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/.well-known/apple-app-site-association", include_in_schema=False)
async def apple_app_site_association() -> JSONResponse:
    """Serve the Apple App Site Association file for Universal Links (Phase 19 / D-03).

    Apple's CDN fetches this at app install time to verify the association between
    the domain and the iOS app. Must be served directly as JSON with no redirects.
    """
    settings = Settings()
    return JSONResponse(
        content={
            "applinks": {
                "apps": [],
                "details": [
                    {
                        "appID": f"{settings.apple_team_id}.{settings.apple_bundle_id}",
                        "paths": ["/pair", "/pair/*", "/oauth/success"],
                    }
                ],
            }
        },
        media_type="application/json",
    )


@app.get("/.well-known/assetlinks.json", include_in_schema=False)
async def asset_links() -> JSONResponse:
    """Serve Android App Links assetlinks.json (Phase 20 / MOB-02).

    Android verifies App Links at install time by fetching this file and
    matching the SHA-256 fingerprint(s) against the installed APK's signing
    certificate. Multiple fingerprints (debug + release) supported via
    comma-separated env var.
    """
    settings = Settings()
    fingerprints = [
        fp.strip()
        for fp in settings.android_sha256_fingerprint.split(",")
        if fp.strip()
    ]
    return JSONResponse(
        content=[
            {
                "relation": ["delegate_permission/common.handle_all_urls"],
                "target": {
                    "namespace": "android_app",
                    "package_name": settings.android_package_name,
                    "sha256_cert_fingerprints": fingerprints,
                },
            }
        ],
        media_type="application/json",
    )
