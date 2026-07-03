"""Shared integration-token -> read adapter resolution (audit H3).

Centralizes the "decrypt IntegrationToken -> build a read-only adapter"
logic that was previously duplicated between daily.cli._resolve_email_adapters
and the LiveKit worker (daily.worker.state, which imported that private CLI
helper directly — dragging Typer, input(), and webbrowser into the runtime
worker process just to reuse one function).

daily.briefing.scheduler._build_pipeline_kwargs needs a superset (email +
calendar + Slack message adapters, plus VIP/config/preferences/redis/openai
kwargs) and has its own DB-session mocking contract in its test suite, so it
is not routed through resolve_email_adapters() here — instead it reuses
build_google_credentials() below to remove the one piece of that function
that was duplicated byte-for-byte (Google OAuth Credentials construction).

Executor resolution (daily.orchestrator.nodes._build_executor_for_type) is a
materially different job — it builds write-capable ActionExecutor instances
(not read-only Adapters), with its own known_addresses/granted_scopes
population and per-action-type dispatch — and is left as-is here per the
audit note; unifying it into this module would be a much larger, riskier
change than adapter resolution. It does reuse build_google_credentials()
for its two Google branches to cut down on the Credentials(...) duplication.
"""
from typing import Any

from sqlalchemy import select


def build_google_credentials(
    access_token: str,
    refresh_token: str | None,
    settings: Any,
    scopes: list[str] | None = None,
) -> Any:
    """Build a google.oauth2.credentials.Credentials object from decrypted tokens.

    Pure construction helper — no I/O, no DB access. Used by
    resolve_email_adapters(), briefing/scheduler.py's pipeline adapter
    resolution, and orchestrator/nodes.py's Google executor branches, all of
    which previously built this object inline with slightly different
    (but equivalent) kwargs.

    Args:
        access_token: Decrypted access token.
        refresh_token: Decrypted refresh token, or None if not stored.
        settings: Settings instance providing google_client_id/secret.
        scopes: Optional granted OAuth scopes list.

    Returns:
        A google.oauth2.credentials.Credentials instance.
    """
    from google.oauth2.credentials import Credentials

    return Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=scopes,
    )


async def resolve_email_adapters(user_id: int, settings: Any) -> list:
    """Load integration tokens and instantiate real email adapters.

    Used by the CLI chat session (daily.cli) and the LiveKit worker bootstrap
    (daily.worker.state) — both need only email adapters (thread
    summarisation / draft style-matching), not calendar or Slack adapters.
    See daily.briefing.scheduler._build_pipeline_kwargs for the briefing
    pipeline's superset need (email + calendar + message adapters).

    Tokens are decrypted in-memory only — never logged (T-03-12).

    Args:
        user_id: User whose integration tokens to load.
        settings: Settings instance providing vault_key.

    Returns:
        List of EmailAdapter instances (GmailAdapter, OutlookAdapter).
        Empty list if no tokens are stored or vault_key is unset.
    """
    from daily.db.engine import async_session
    from daily.db.models import IntegrationToken
    from daily.integrations.google.adapter import GmailAdapter
    from daily.integrations.microsoft.adapter import OutlookAdapter
    from daily.vault.crypto import decrypt_token, load_vault_key

    vault_key = load_vault_key(settings.vault_key)
    adapters: list = []

    async with async_session() as session:
        result = await session.execute(
            select(IntegrationToken).where(IntegrationToken.user_id == user_id)
        )
        tokens = result.scalars().all()

    for token in tokens:
        try:
            decrypted = decrypt_token(token.encrypted_access_token, vault_key)
            if token.provider == "google":
                refresh_token = (
                    decrypt_token(token.encrypted_refresh_token, vault_key)
                    if token.encrypted_refresh_token else None
                )
                creds = build_google_credentials(
                    access_token=decrypted,
                    refresh_token=refresh_token,
                    settings=settings,
                    scopes=token.scopes.split() if token.scopes else None,
                )
                adapters.append(GmailAdapter(credentials=creds))
            elif token.provider == "outlook":
                adapters.append(OutlookAdapter(access_token=decrypted))
        except Exception:
            # Skip tokens that fail decryption — don't block the session
            pass

    return adapters
