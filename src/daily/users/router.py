"""Per-user preferences and integration-status endpoints (Phase 21)."""
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from daily.auth.deps import get_current_user
from daily.briefing.scheduler import setup_scheduler_for_user
from daily.db.engine import async_session
from daily.db.models import BriefingConfig, IntegrationToken, User

router = APIRouter(prefix="/users", tags=["users"])


async def _get_db() -> AsyncSession:
    async with async_session() as session:
        yield session


# ---------------------------------------------------------------------------
# GET /users/me/integrations
# ---------------------------------------------------------------------------


class IntegrationStatusResponse(BaseModel):
    google: bool
    microsoft: bool
    slack: bool


@router.get("/me/integrations", response_model=IntegrationStatusResponse)
async def get_integration_status(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_db),
) -> IntegrationStatusResponse:
    """Return boolean integration status per provider for the current user.

    DB provider strings:
    - "google"  → google: true
    - "outlook" → microsoft: true  (canonical Microsoft key is "outlook" in DB)
    - "slack"   → slack: true
    """
    result = await session.execute(
        select(IntegrationToken.provider).where(
            IntegrationToken.user_id == current_user.id
        )
    )
    connected = {row[0] for row in result.fetchall()}
    return IntegrationStatusResponse(
        google="google" in connected,
        microsoft="outlook" in connected,  # provider="outlook" maps to microsoft
        slack="slack" in connected,
    )


# ---------------------------------------------------------------------------
# PUT /users/me/preferences
# ---------------------------------------------------------------------------


class PreferencesUpdateRequest(BaseModel):
    briefing_time: str = Field(..., description="Local briefing time in HH:MM (24h) format")
    timezone: str = Field(..., description="IANA timezone string e.g. 'Australia/Brisbane'")

    @field_validator("briefing_time")
    @classmethod
    def validate_time(cls, v: str) -> str:
        parts = v.split(":")
        if len(parts) != 2:
            raise ValueError("briefing_time must be HH:MM")
        try:
            h, m = int(parts[0]), int(parts[1])
        except ValueError as exc:
            raise ValueError("briefing_time must contain integer hour and minute") from exc
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError("briefing_time hour must be 0-23, minute 0-59")
        return v


def _parse_local_hm(time_str: str, tz_name: str) -> tuple[int, int]:
    """Validate the IANA timezone and parse HH:MM into (hour, minute).

    Audit M1 fix: this used to convert local HH:MM to a fixed UTC hour/minute
    at write time (see git history for `_local_to_utc_hm`). That fixed UTC
    value goes stale the moment the local zone crosses a DST boundary — e.g. a
    7am Sydney briefing computed as 21:00 UTC (prev day) during AEST silently
    fires at 8am local once AEDT starts, because the stored UTC hour never
    changes. Storing the LOCAL hour/minute + IANA timezone instead, and
    letting APScheduler's CronTrigger resolve them against that zone on every
    fire (see scheduler.setup_scheduler_for_user), makes DST handling correct
    by construction — the timezone rule lives in one place (zoneinfo), not
    baked into a stale offset.

    Raises HTTPException 422 for unknown timezone strings.
    """
    try:
        ZoneInfo(tz_name)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(status_code=422, detail=f"Unknown timezone: {tz_name}") from exc
    h, m = map(int, time_str.split(":"))
    return h, m


@router.put("/me/preferences", status_code=204)
async def update_preferences(
    body: PreferencesUpdateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_db),
) -> None:
    """Upsert BriefingConfig with LOCAL schedule time + IANA timezone (DST-safe).

    Stores the user-supplied briefing time as-is (local wall-clock hour/minute)
    alongside the IANA timezone string — see _parse_local_hm for why this
    replaced the previous "convert to UTC at write time" approach (audit M1:
    that approach went stale across DST transitions).

    Audit M1 fix: also live-reschedules the running APScheduler job right
    after the DB commit, via setup_scheduler_for_user. Previously this endpoint
    only wrote to the DB — the in-process scheduler kept firing at the OLD
    time until the next app restart, so a changed briefing time silently had
    no effect until someone happened to redeploy.

    Returns 204 No Content on success; 422 if timezone is unknown.
    """
    hour, minute = _parse_local_hm(body.briefing_time, body.timezone)

    result = await session.execute(
        select(BriefingConfig).where(BriefingConfig.user_id == current_user.id)
    )
    config = result.scalar_one_or_none()
    if config is None:
        config = BriefingConfig(user_id=current_user.id)
        session.add(config)
    config.schedule_hour = hour
    config.schedule_minute = minute
    config.timezone = body.timezone
    await session.commit()

    # Live reschedule (audit M1) — apply immediately, no app restart required.
    setup_scheduler_for_user(
        hour=hour, minute=minute, user_id=current_user.id, timezone=body.timezone
    )
    return None
