"""Wave 0 test scaffold for GET /integrations/* endpoints (Plan 21-02).

All tests are marked skip — they will be unskipped as Plan 03 implements
the ``daily.integrations.router`` module. Imports of the not-yet-existing
module are placed *inside* each test function so pytest collection succeeds
before Plan 03 lands.

Test map: INT-01 through INT-07 from 21-RESEARCH.md, plus an auth gate test.
"""
import pytest


# ---------------------------------------------------------------------------
# INT-01: GET /integrations/google/connect
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="MISSING — implemented in Plan 03")
@pytest.mark.asyncio
async def test_google_connect():
    """INT-01: GET /integrations/google/connect with valid Bearer token.

    Expects:
    - HTTP 200
    - Response JSON contains ``auth_url`` field (Google OAuth authorization URL)
    - Redis key ``oauth_state:{state}`` is set with TTL <= 600 s
    """
    from daily.integrations.router import router as integrations_router  # noqa: F401

    pytest.skip("Plan 03 — pending implementation")


# ---------------------------------------------------------------------------
# INT-02: GET /integrations/google/callback
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="MISSING — implemented in Plan 03")
@pytest.mark.asyncio
async def test_google_callback():
    """INT-02: GET /integrations/google/callback?code=X&state=Y.

    With a valid state value stored in Redis, the callback must:
    - Exchange ``code`` for tokens via the Google OAuth endpoint
    - Encrypt and store the token as an ``IntegrationToken`` row (provider="google")
    - Return HTTP 302 redirect to ``/oauth/success?provider=google``
    """
    from daily.integrations.router import router as integrations_router  # noqa: F401

    pytest.skip("Plan 03 — pending implementation")


# ---------------------------------------------------------------------------
# INT-03: GET /integrations/microsoft/connect
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="MISSING — implemented in Plan 03")
@pytest.mark.asyncio
async def test_microsoft_connect():
    """INT-03: GET /integrations/microsoft/connect returns 200 with ``auth_url``."""
    from daily.integrations.router import router as integrations_router  # noqa: F401

    pytest.skip("Plan 03 — pending implementation")


# ---------------------------------------------------------------------------
# INT-04: GET /integrations/microsoft/callback
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="MISSING — implemented in Plan 03")
@pytest.mark.asyncio
async def test_microsoft_callback():
    """INT-04: Microsoft callback exchanges code via msal mock.

    Stores ``IntegrationToken`` with ``provider="outlook"`` (NOT "microsoft")
    to match the existing vault / token-refresh conventions.
    """
    from daily.integrations.router import router as integrations_router  # noqa: F401

    pytest.skip("Plan 03 — pending implementation")


# ---------------------------------------------------------------------------
# INT-05: GET /integrations/slack/connect
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="MISSING — implemented in Plan 03")
@pytest.mark.asyncio
async def test_slack_connect():
    """INT-05: GET /integrations/slack/connect returns 200 with ``auth_url``."""
    from daily.integrations.router import router as integrations_router  # noqa: F401

    pytest.skip("Plan 03 — pending implementation")


# ---------------------------------------------------------------------------
# INT-06: GET /integrations/slack/callback
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="MISSING — implemented in Plan 03")
@pytest.mark.asyncio
async def test_slack_callback():
    """INT-06: Slack callback uses async httpx to POST to ``oauth.v2.access``.

    Stores the Slack token with ``provider="slack"``.
    """
    from daily.integrations.router import router as integrations_router  # noqa: F401

    pytest.skip("Plan 03 — pending implementation")


# ---------------------------------------------------------------------------
# INT-07: Invalid state returns 400
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="MISSING — implemented in Plan 03")
@pytest.mark.asyncio
async def test_invalid_state():
    """INT-07: Callback with a state value not found in Redis returns HTTP 400."""
    from daily.integrations.router import router as integrations_router  # noqa: F401

    pytest.skip("Plan 03 — pending implementation")


# ---------------------------------------------------------------------------
# Auth gate: unauthenticated request returns 401
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="MISSING — implemented in Plan 03")
@pytest.mark.asyncio
async def test_connect_requires_auth():
    """GET /integrations/google/connect without a Bearer token returns HTTP 401."""
    from daily.integrations.router import router as integrations_router  # noqa: F401

    pytest.skip("Plan 03 — pending implementation")
