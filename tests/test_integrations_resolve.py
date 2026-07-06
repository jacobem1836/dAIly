"""Tests for daily.integrations.resolve — shared adapter resolution (audit H3).

Covers:
- resolve_email_adapters() builds GmailAdapter for google tokens and
  OutlookAdapter for outlook tokens (regression test for a latent bug where
  the pre-refactor daily.cli._resolve_email_adapters checked
  `token.provider == "microsoft"`, which never matches the actual stored
  provider string "outlook" — see daily.integrations.microsoft.auth — so
  Outlook adapters were silently never built for the CLI chat / LiveKit
  worker bootstrap paths).
- A token that fails decryption is skipped without blocking other tokens.
- build_google_credentials() is a pure passthrough construction helper.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_token(provider: str, scopes: str | None = "scope.a scope.b"):
    token = MagicMock()
    token.provider = provider
    token.encrypted_access_token = f"enc-access-{provider}"
    token.encrypted_refresh_token = f"enc-refresh-{provider}" if provider == "google" else None
    token.scopes = scopes
    return token


def _mock_session_ctx(tokens):
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = tokens

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=mock_ctx)


@pytest.mark.asyncio
async def test_resolve_email_adapters_builds_gmail_for_google_token():
    """A stored 'google' token produces a GmailAdapter."""
    from daily.config import Settings
    from daily.integrations.resolve import resolve_email_adapters

    google_token = _make_token("google")

    with (
        patch("daily.db.engine.async_session", _mock_session_ctx([google_token])),
        patch("daily.vault.crypto.load_vault_key", return_value=b"k" * 32),
        patch("daily.vault.crypto.decrypt_token", side_effect=lambda enc, key: f"plain:{enc}"),
        patch("daily.integrations.google.adapter.GmailAdapter") as mock_gmail,
    ):
        settings = Settings(
            redis_url="redis://localhost:6379/0",
            openai_api_key="test-key",
            vault_key="dGVzdC12YXVsdC1rZXktMzItYnl0ZXMtbG9uZyEh",
        )
        adapters = await resolve_email_adapters(user_id=1, settings=settings)

    mock_gmail.assert_called_once()
    assert len(adapters) == 1


@pytest.mark.asyncio
async def test_resolve_email_adapters_builds_outlook_for_outlook_token():
    """A stored 'outlook' token produces an OutlookAdapter (regression: not 'microsoft').

    Before this module existed, daily.cli._resolve_email_adapters checked
    `token.provider == "microsoft"`, but the actual provider string persisted
    by daily.integrations.microsoft.auth.store_microsoft_tokens is "outlook" —
    so this branch never matched in practice. Unifying the logic here fixes it.
    """
    from daily.config import Settings
    from daily.integrations.resolve import resolve_email_adapters

    outlook_token = _make_token("outlook")

    with (
        patch("daily.db.engine.async_session", _mock_session_ctx([outlook_token])),
        patch("daily.vault.crypto.load_vault_key", return_value=b"k" * 32),
        patch("daily.vault.crypto.decrypt_token", side_effect=lambda enc, key: f"plain:{enc}"),
        patch("daily.integrations.microsoft.adapter.OutlookAdapter") as mock_outlook,
    ):
        settings = Settings(
            redis_url="redis://localhost:6379/0",
            openai_api_key="test-key",
            vault_key="dGVzdC12YXVsdC1rZXktMzItYnl0ZXMtbG9uZyEh",
        )
        adapters = await resolve_email_adapters(user_id=1, settings=settings)

    mock_outlook.assert_called_once_with(access_token="plain:enc-access-outlook")
    assert len(adapters) == 1


@pytest.mark.asyncio
async def test_resolve_email_adapters_skips_token_that_fails_decryption():
    """A token whose decryption raises is skipped, not fatal to the whole call."""
    from daily.config import Settings
    from daily.integrations.resolve import resolve_email_adapters

    bad_token = _make_token("google")
    good_token = _make_token("outlook")

    with (
        patch(
            "daily.db.engine.async_session",
            _mock_session_ctx([bad_token, good_token]),
        ),
        patch("daily.vault.crypto.load_vault_key", return_value=b"k" * 32),
        patch(
            "daily.vault.crypto.decrypt_token",
            side_effect=lambda enc, key: (
                (_ for _ in ()).throw(ValueError("bad ciphertext"))
                if "google" in enc
                else f"plain:{enc}"
            ),
        ),
        patch("daily.integrations.microsoft.adapter.OutlookAdapter") as mock_outlook,
    ):
        settings = Settings(
            redis_url="redis://localhost:6379/0",
            openai_api_key="test-key",
            vault_key="dGVzdC12YXVsdC1rZXktMzItYnl0ZXMtbG9uZyEh",
        )
        adapters = await resolve_email_adapters(user_id=1, settings=settings)

    mock_outlook.assert_called_once()
    assert len(adapters) == 1


def test_build_google_credentials_passes_through_fields():
    """build_google_credentials constructs a Credentials object from decrypted values."""
    from daily.integrations.resolve import build_google_credentials

    settings = MagicMock(google_client_id="client-id", google_client_secret="client-secret")

    creds = build_google_credentials(
        access_token="access-tok",
        refresh_token="refresh-tok",
        settings=settings,
        scopes=["scope.a"],
    )

    assert creds.token == "access-tok"
    assert creds.refresh_token == "refresh-tok"
    assert creds.client_id == "client-id"
    assert creds.client_secret == "client-secret"
    assert creds.scopes == ["scope.a"]
