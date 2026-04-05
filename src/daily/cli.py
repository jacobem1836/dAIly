"""
dAIly CLI entrypoint.

Entry point: `daily` command (defined in pyproject.toml [project.scripts]).

Commands:
    daily connect gmail     -- Connect Gmail account via Google OAuth (Plan 03)
    daily connect calendar  -- Connect Google Calendar via Google OAuth (Plan 03)
    daily connect slack     -- Connect Slack workspace via OAuth (Plan 04)
    daily connect outlook   -- Connect Microsoft Outlook via OAuth (Plan 05)
"""

import asyncio
import base64

import typer

app = typer.Typer(name="daily", help="dAIly - AI personal assistant")
connect_app = typer.Typer(help="Connect integration accounts")
app.add_typer(connect_app, name="connect")


@connect_app.command()
def gmail():
    """Connect Gmail and Google Calendar accounts via Google OAuth."""
    from daily.config import Settings
    from daily.db.engine import make_engine, make_session_factory
    from daily.integrations.google.auth import (
        GOOGLE_READONLY_SCOPES,
        run_google_oauth_flow,
        store_google_tokens,
    )

    settings = Settings()

    if not settings.google_client_id or not settings.google_client_secret:
        typer.echo(
            "Error: GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set in .env",
            err=True,
        )
        raise typer.Exit(1)

    vault_key = base64.b64decode(settings.vault_key) if settings.vault_key else b""
    if len(vault_key) != 32:
        typer.echo(
            "Error: VAULT_KEY must be a 32-byte base64-encoded key", err=True
        )
        raise typer.Exit(1)

    typer.echo("Opening browser for Google OAuth authorization...")
    typer.echo("Scopes: Gmail (readonly) + Google Calendar (readonly)")

    credentials = run_google_oauth_flow(
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=GOOGLE_READONLY_SCOPES,
    )

    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)

    # Default to user_id=1 for Phase 1 single-user setup
    asyncio.run(
        store_google_tokens(
            credentials=credentials,
            user_id=1,
            vault_key=vault_key,
            session_factory=session_factory,
        )
    )

    typer.echo("Google OAuth complete. Gmail and Google Calendar connected.")


@connect_app.command()
def calendar():
    """Connect Google Calendar via Google OAuth.

    Google Calendar access is included with the Gmail connection.
    Run `daily connect gmail` to authorize both Gmail and Google Calendar.
    """
    typer.echo(
        "Google Calendar access is included with Gmail connection — run `daily connect gmail`"
    )


@connect_app.command()
def slack():
    """Connect Slack workspace via OAuth."""
    from daily.config import Settings
    from daily.db.engine import make_engine, make_session_factory
    from daily.integrations.slack.auth import (
        SLACK_BOT_SCOPES,
        run_slack_oauth_flow,
        store_slack_token,
    )

    settings = Settings()

    if not settings.slack_client_id or not settings.slack_client_secret:
        typer.echo(
            "Error: SLACK_CLIENT_ID and SLACK_CLIENT_SECRET must be set in .env",
            err=True,
        )
        raise typer.Exit(1)

    vault_key = base64.b64decode(settings.vault_key) if settings.vault_key else b""
    if len(vault_key) != 32:
        typer.echo(
            "Error: VAULT_KEY must be a 32-byte base64-encoded key", err=True
        )
        raise typer.Exit(1)

    scopes_display = ", ".join(SLACK_BOT_SCOPES)
    typer.echo("Opening browser for Slack OAuth authorization...")
    typer.echo(f"Scopes: {scopes_display}")

    bot_token = run_slack_oauth_flow(
        client_id=settings.slack_client_id,
        client_secret=settings.slack_client_secret,
    )

    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)

    # Default to user_id=1 for Phase 1 single-user setup
    asyncio.run(
        store_slack_token(
            bot_token=bot_token,
            user_id=1,
            vault_key=vault_key,
            session_factory=session_factory,
        )
    )

    typer.echo("Slack OAuth complete. Slack workspace connected.")


@connect_app.command()
def outlook():
    """Connect Microsoft Outlook via OAuth."""
    from daily.config import Settings
    from daily.db.engine import make_engine, make_session_factory
    from daily.integrations.microsoft.auth import (
        MICROSOFT_READONLY_SCOPES,
        run_microsoft_oauth_flow,
        store_microsoft_tokens,
    )

    settings = Settings()

    if not settings.microsoft_client_id or not settings.microsoft_tenant_id:
        typer.echo(
            "Error: MICROSOFT_CLIENT_ID and MICROSOFT_TENANT_ID must be set in .env",
            err=True,
        )
        raise typer.Exit(1)

    vault_key = base64.b64decode(settings.vault_key) if settings.vault_key else b""
    if len(vault_key) != 32:
        typer.echo(
            "Error: VAULT_KEY must be a 32-byte base64-encoded key", err=True
        )
        raise typer.Exit(1)

    scopes_display = ", ".join(MICROSOFT_READONLY_SCOPES)
    typer.echo("Opening browser for Microsoft OAuth authorization...")
    typer.echo(f"Scopes: {scopes_display}")

    result = run_microsoft_oauth_flow(
        client_id=settings.microsoft_client_id,
        tenant_id=settings.microsoft_tenant_id,
    )

    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)

    # Default to user_id=1 for Phase 1 single-user setup
    asyncio.run(
        store_microsoft_tokens(
            result=result,
            user_id=1,
            vault_key=vault_key,
            session_factory=session_factory,
        )
    )

    typer.echo("Microsoft OAuth complete. Outlook connected.")


if __name__ == "__main__":
    app()
