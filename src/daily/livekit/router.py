"""LiveKit token endpoint (Phase 18, INFRA-02 / D-03)."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from daily.auth.deps import get_current_user
from daily.config import Settings
from daily.db.models import User
from daily.livekit.tokens import create_livekit_token

router = APIRouter(prefix="/livekit", tags=["livekit"])


def _get_settings() -> Settings:
    return Settings()


class LiveKitTokenResponse(BaseModel):
    token: str
    room: str
    livekit_url: str


@router.post("/token", response_model=LiveKitTokenResponse)
async def get_livekit_token(
    current_user: User = Depends(get_current_user),
    settings: Settings = Depends(_get_settings),
) -> LiveKitTokenResponse:
    token, room = create_livekit_token(current_user.id, settings)
    return LiveKitTokenResponse(
        token=token,
        room=room,
        livekit_url=settings.livekit_url,
    )
