"""Per-user preferences and integration-status endpoints (Phase 21)."""
from datetime import datetime, timezone as _tz
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from daily.auth.deps import get_current_user
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


def _local_to_utc_hm(time_str: str, tz_name: str) -> tuple[int, int]:
    """Convert local HH:MM + IANA timezone to UTC (hour, minute).

    Raises HTTPException 422 for unknown timezone strings.
    """
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(status_code=422, detail=f"Unknown timezone: {tz_name}") from exc
    h, m = map(int, time_str.split(":"))
    local_now = datetime.now(tz).replace(hour=h, minute=m, second=0, microsecond=0)
    utc = local_now.astimezone(_tz.utc)
    return utc.hour, utc.minute


@router.put("/me/preferences", status_code=204)
async def update_preferences(
    body: PreferencesUpdateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_db),
) -> None:
    """Upsert BriefingConfig with UTC-converted schedule time + IANA timezone.

    Converts the user-supplied local briefing time to UTC using zoneinfo.ZoneInfo.
    Stores the IANA timezone string verbatim for display/DST purposes.
    Returns 204 No Content on success; 422 if timezone is unknown.
    """
    utc_hour, utc_minute = _local_to_utc_hm(body.briefing_time, body.timezone)

    result = await session.execute(
        select(BriefingConfig).where(BriefingConfig.user_id == current_user.id)
    )
    config = result.scalar_one_or_none()
    if config is None:
        config = BriefingConfig(user_id=current_user.id)
        session.add(config)
    config.schedule_hour = utc_hour
    config.schedule_minute = utc_minute
    config.timezone = body.timezone
    await session.commit()
    return None
