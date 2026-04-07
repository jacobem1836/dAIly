"""
dAIly CLI entrypoint.

Entry point: `daily` command (defined in pyproject.toml [project.scripts]).

Commands:
    daily connect gmail     -- Connect Gmail account via Google OAuth (Plan 03)
    daily connect calendar  -- Connect Google Calendar via Google OAuth (Plan 03)
    daily connect slack     -- Connect Slack workspace via OAuth (Plan 04)
    daily connect outlook   -- Connect Microsoft Outlook via OAuth (Plan 05)
    daily config set        -- Set a briefing config value (D-16)
    daily vip add           -- Add a VIP sender email (D-16)
    daily vip remove        -- Remove a VIP sender email (D-16)
    daily vip list          -- List all VIP sender emails (D-16)

CLI async/sync bridge: all DB-touching commands use asyncio.run() to bridge
the synchronous Typer context to the async SQLAlchemy engine. This avoids
needing a separate sync engine or psycopg2 dependency (per D-16 review).
"""

import asyncio
import base64

import typer

app = typer.Typer(name="daily", help="dAIly - AI personal assistant")
connect_app = typer.Typer(help="Connect integration accounts")
app.add_typer(connect_app, name="connect")

config_app = typer.Typer(help="Configure briefing settings")
app.add_typer(config_app, name="config")

vip_app = typer.Typer(help="Manage VIP sender list")
app.add_typer(vip_app, name="vip")


# ---------------------------------------------------------------------------
# Async helpers for config commands (bridged via asyncio.run)
# ---------------------------------------------------------------------------

async def _upsert_config(user_id: int, key: str, value: str) -> str:
    """Async helper for config upsert. Called via asyncio.run() from CLI.

    Supported keys:
      briefing.schedule_time  -- format HH:MM (e.g. "05:30")
      briefing.email_top_n    -- integer (e.g. "5")
    """
    from sqlalchemy import select

    from daily.db.engine import async_session
    from daily.db.models import BriefingConfig

    async with async_session() as session:
        result = await session.execute(
            select(BriefingConfig).where(BriefingConfig.user_id == user_id)
        )
        config = result.scalar_one_or_none()
        if config is None:
            config = BriefingConfig(user_id=user_id)
            session.add(config)

        if key == "briefing.schedule_time":
            parts = value.split(":")
            if len(parts) != 2:
                return f"Invalid format for briefing.schedule_time. Expected HH:MM, got: {value}"
            config.schedule_hour = int(parts[0])
            config.schedule_minute = int(parts[1])
        elif key == "briefing.email_top_n":
            config.email_top_n = int(value)
        else:
            return f"Unknown config key: {key}. Supported: briefing.schedule_time, briefing.email_top_n"

        await session.commit()
        return f"Set {key} = {value}"


async def _add_vip(user_id: int, email: str) -> str:
    """Async helper to add a VIP sender. Called via asyncio.run() from CLI."""
    from daily.db.engine import async_session
    from daily.db.models import VipSender

    async with async_session() as session:
        sender = VipSender(user_id=user_id, email=email.lower().strip())
        session.add(sender)
        await session.commit()
        return f"Added VIP: {email}"


async def _remove_vip(user_id: int, email: str) -> str:
    """Async helper to remove a VIP sender. Called via asyncio.run() from CLI."""
    from sqlalchemy import delete

    from daily.db.engine import async_session
    from daily.db.models import VipSender

    async with async_session() as session:
        await session.execute(
            delete(VipSender).where(
                VipSender.user_id == user_id,
                VipSender.email == email.lower().strip(),
            )
        )
        await session.commit()
        return f"Removed VIP: {email}"


async def _list_vips(user_id: int) -> list[str]:
    """Async helper to list VIP senders. Called via asyncio.run() from CLI."""
    from sqlalchemy import select

    from daily.db.engine import async_session
    from daily.db.models import VipSender

    async with async_session() as session:
        result = await session.execute(
            select(VipSender.email).where(VipSender.user_id == user_id)
        )
        return [row[0] for row in result.fetchall()]


# ---------------------------------------------------------------------------
# Config commands
# ---------------------------------------------------------------------------

@config_app.command("set")
def config_set(key: str, value: str):
    """Set a briefing config value.

    Keys:
      briefing.schedule_time  -- daily precompute time, format HH:MM (UTC)
      briefing.email_top_n    -- number of top emails to include in briefing

    Examples:
      daily config set briefing.schedule_time 06:00
      daily config set briefing.email_top_n 10
    """
    result = asyncio.run(_upsert_config(user_id=1, key=key, value=value))
    typer.echo(result)


# ---------------------------------------------------------------------------
# VIP commands
# ---------------------------------------------------------------------------

@vip_app.command("add")
def vip_add(email: str):
    """Add an email address to the VIP sender list.

    VIP senders receive a priority boost in email ranking.

    Example:
      daily vip add boss@company.com
    """
    result = asyncio.run(_add_vip(user_id=1, email=email))
    typer.echo(result)


@vip_app.command("remove")
def vip_remove(email: str):
    """Remove an email address from the VIP sender list.

    Example:
      daily vip remove boss@company.com
    """
    result = asyncio.run(_remove_vip(user_id=1, email=email))
    typer.echo(result)


@vip_app.command("list")
def vip_list():
    """List all VIP sender email addresses."""
    vips = asyncio.run(_list_vips(user_id=1))
    for v in vips:
        typer.echo(v)
    if not vips:
        typer.echo("No VIP senders configured.")


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
