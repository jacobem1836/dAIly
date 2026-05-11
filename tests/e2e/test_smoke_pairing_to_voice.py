"""E2E smoke test: pairing → onboarding (Google OAuth) → voice token.

Exercises the full new-user happy path against the full FastAPI app in a single
test function. External services are mocked at their HTTP/SDK boundaries.

Steps:
  1. Send magic link (POST /auth/pair/send-link) — 204
  2. Extract pairing code from DB
  3. Complete pairing (POST /auth/pair/complete) — 200 with tokens
  4. Connect Google integration (GET /integrations/google/connect) — 200
  5. Simulate Google OAuth callback — 302 redirect
  6. Set briefing schedule (PUT /users/me/preferences) — 204
  7. Read integration status (GET /users/me/integrations) — 200, google=True
  8. Issue LiveKit token (POST /livekit/token) — 200 with JWT-shaped token
  9. Refresh access token (POST /auth/token/refresh) — 200 with new token
"""
import pytest
from sqlalchemy import select

from daily.db.models import IntegrationToken, PairingCode, User


@pytest.mark.e2e
async def test_full_user_onboarding_to_voice_connect(client, mock_resend, mock_oauth_exchange, db_factory):
    """Full new-user flow: magic link → pairing → Google OAuth → prefs → voice token → refresh."""
    ac, fake_redis, db_factory = client

    # -------------------------------------------------------------------------
    # Step 1: Send magic link
    # -------------------------------------------------------------------------
    resp = await ac.post(
        "/auth/pair/send-link",
        json={"email": "newuser@test.com"},
    )
    assert resp.status_code == 204, resp.text

    # Assert mock_resend was called once with the correct email
    assert len(mock_resend) == 1, f"Expected 1 send_magic_link call, got {len(mock_resend)}"
    sent_email, sent_code = mock_resend[0]
    assert sent_email == "newuser@test.com"
    assert len(sent_code) == 6 and sent_code.isdigit(), f"Invalid code: {sent_code!r}"

    # -------------------------------------------------------------------------
    # Step 2: Extract pairing code from DB (the code was stored before email send)
    # -------------------------------------------------------------------------
    async with db_factory() as session:
        result = await session.execute(
            select(PairingCode).where(PairingCode.email == "newuser@test.com")
        )
        pairing_row = result.scalar_one()
    code = pairing_row.code
    assert len(code) == 6 and code.isdigit()

    # -------------------------------------------------------------------------
    # Step 3: Complete pairing
    # -------------------------------------------------------------------------
    resp = await ac.post(
        "/auth/pair/complete",
        json={"code": code, "device_name": "iPhone Test"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "access_token" in body, f"Missing access_token: {body}"
    assert "refresh_token" in body, f"Missing refresh_token: {body}"
    assert "expires_in" in body, f"Missing expires_in: {body}"

    access_token = body["access_token"]
    refresh_token = body["refresh_token"]
    auth_headers = {"Authorization": f"Bearer {access_token}"}

    # -------------------------------------------------------------------------
    # Step 4: Connect Google integration — get the authorize_url
    # -------------------------------------------------------------------------
    resp = await ac.get("/integrations/google/connect", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    connect_body = resp.json()
    assert "auth_url" in connect_body, f"Missing auth_url: {connect_body}"
    assert connect_body["auth_url"], "auth_url must be non-empty"

    # Extract the state from Redis (stored by the connect endpoint)
    state_keys = await fake_redis.keys("oauth_state:*")
    assert len(state_keys) == 1, f"Expected 1 oauth_state key, got {state_keys}"
    state = state_keys[0].decode().split("oauth_state:")[-1]

    # -------------------------------------------------------------------------
    # Step 5: Simulate Google OAuth callback
    # The mock_oauth_exchange fixture already patches Flow so fetch_token succeeds.
    # -------------------------------------------------------------------------
    resp = await ac.get(
        f"/integrations/google/callback?code=fake-auth-code&state={state}",
        follow_redirects=False,
    )
    # Callback returns a 302 redirect to the app deep link
    assert resp.status_code == 302, resp.text

    # Verify IntegrationToken was created for Google
    async with db_factory() as session:
        result = await session.execute(
            select(IntegrationToken).where(
                IntegrationToken.provider == "google"
            )
        )
        token_row = result.scalar_one_or_none()
    assert token_row is not None, "IntegrationToken for google not created"

    # -------------------------------------------------------------------------
    # Step 6: Set briefing schedule
    # -------------------------------------------------------------------------
    resp = await ac.put(
        "/users/me/preferences",
        json={"briefing_time": "07:30", "timezone": "Australia/Brisbane"},
        headers=auth_headers,
    )
    assert resp.status_code == 204, resp.text

    # -------------------------------------------------------------------------
    # Step 7: Read integration status
    # -------------------------------------------------------------------------
    resp = await ac.get("/users/me/integrations", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    status_body = resp.json()
    assert status_body["google"] is True, f"google should be True: {status_body}"

    # -------------------------------------------------------------------------
    # Step 8: Issue LiveKit token
    # -------------------------------------------------------------------------
    resp = await ac.post("/livekit/token", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    livekit_body = resp.json()
    assert "token" in livekit_body, f"Missing token field: {livekit_body}"
    token_parts = livekit_body["token"].split(".")
    assert len(token_parts) == 3, f"LiveKit token is not JWT-shaped (3 parts): {livekit_body['token']!r}"

    # -------------------------------------------------------------------------
    # Step 9: Refresh access token
    # -------------------------------------------------------------------------
    resp = await ac.post(
        "/auth/token/refresh",
        json={"refresh_token": refresh_token},
    )
    assert resp.status_code == 200, resp.text
    refresh_body = resp.json()
    assert "access_token" in refresh_body, f"Missing access_token in refresh: {refresh_body}"
    # New token is valid JWT-shaped (may match original if issued within same second — that is acceptable)
    new_token_parts = refresh_body["access_token"].split(".")
    assert len(new_token_parts) == 3, f"Refreshed access_token is not JWT-shaped: {refresh_body['access_token']!r}"
