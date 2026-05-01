"""Wave 0 test scaffold for GET/PUT /users/me/* endpoints (Plan 21-02).

All tests are marked skip — they will be unskipped as Plan 04 implements
the ``daily.users.router`` module. Imports of the not-yet-existing module
are placed *inside* each test function so pytest collection succeeds
before Plan 04 lands.

Test map: USR-01 through USR-03 from 21-RESEARCH.md.
"""
import pytest


# ---------------------------------------------------------------------------
# USR-01: GET /users/me/integrations
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="MISSING — implemented in Plan 04")
@pytest.mark.asyncio
async def test_integration_status():
    """USR-01: GET /users/me/integrations with auth returns integration status map.

    Expects:
    - HTTP 200
    - Response JSON: ``{google: bool, microsoft: bool, slack: bool}``
    - Values reflect whether ``IntegrationToken`` rows exist for the current user
    - ``provider="outlook"`` row maps to ``microsoft: true`` (not "microsoft")
    """
    from daily.users.router import router as users_router  # noqa: F401

    pytest.skip("Plan 04 — pending implementation")


# ---------------------------------------------------------------------------
# USR-02: PUT /users/me/preferences
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="MISSING — implemented in Plan 04")
@pytest.mark.asyncio
async def test_update_preferences():
    """USR-02: PUT /users/me/preferences upserts BriefingConfig row.

    Request body: ``{briefing_time: "07:00", timezone: "Australia/Brisbane"}``

    Expects:
    - HTTP 200
    - ``BriefingConfig`` row upserted with UTC-converted ``schedule_hour``/
      ``schedule_minute`` and IANA ``timezone`` string stored verbatim
    """
    from daily.users.router import router as users_router  # noqa: F401

    pytest.skip("Plan 04 — pending implementation")


# ---------------------------------------------------------------------------
# USR-03: PUT /users/me/preferences — invalid timezone
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="MISSING — implemented in Plan 04")
@pytest.mark.asyncio
async def test_invalid_timezone():
    """USR-03: PUT /users/me/preferences with timezone="Not/A_Zone" returns HTTP 422."""
    from daily.users.router import router as users_router  # noqa: F401

    pytest.skip("Plan 04 — pending implementation")
