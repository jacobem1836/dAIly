"""
Briefing on-demand trigger endpoint (D-04, Plan 21.2-01).

POST /briefings/trigger — authenticated endpoint that runs the full briefing
pipeline synchronously for the current user. Called by the iOS client at the
end of onboarding so a cached briefing is ready immediately, before the cron
schedule fires.

Design decisions:
  - Synchronous (blocking) — iOS shows a spinner while waiting (15-30s acceptable).
  - Reuses _build_pipeline_kwargs from scheduler.py to resolve all adapters,
    Redis, and OpenAI client identically to the cron-scheduled run.
  - Returns 202 (Accepted) with {"status": "completed"} on success.
  - Returns 500 with sanitised detail "briefing_generation_failed" on pipeline
    error — no token or credential data is included in the response (SEC-T-02).
  - Redis connection is always closed in the finally block to avoid leaks.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from daily.auth.deps import get_current_user
from daily.briefing.pipeline import run_briefing_pipeline
from daily.briefing.scheduler import _build_pipeline_kwargs
from daily.config import Settings
from daily.db.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/briefings", tags=["briefings"])


@router.post("/trigger", status_code=202)
async def trigger_briefing(
    current_user: User = Depends(get_current_user),
) -> dict:
    """Run the briefing pipeline on demand for the authenticated user (D-04).

    Called by the iOS CompletionView at the end of onboarding so the user has
    a cached briefing immediately. Blocks until the pipeline completes.

    Returns:
        {"status": "completed"} on success.

    Raises:
        HTTPException 500: If the pipeline fails. Detail is always
            "briefing_generation_failed" — no raw error data is leaked.
    """
    settings = Settings()
    kwargs: dict = {}
    try:
        kwargs = await _build_pipeline_kwargs(current_user.id, settings)
        await run_briefing_pipeline(user_id=current_user.id, **kwargs)
    except Exception:
        logger.exception(
            "On-demand briefing failed for user_id=%s", current_user.id
        )
        raise HTTPException(
            status_code=500,
            detail="briefing_generation_failed",
        )
    finally:
        redis = kwargs.get("redis")
        if redis is not None:
            await redis.aclose()

    return {"status": "completed"}
