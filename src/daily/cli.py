"""
dAIly CLI entrypoint.

Entry point: `daily` command (defined in pyproject.toml [project.scripts]).

Commands:
    daily connect gmail     -- Connect Gmail account via Google OAuth (Plan 03)
    daily connect calendar  -- Connect Google Calendar via Google OAuth (Plan 03)
    daily connect slack     -- Connect Slack workspace via OAuth (Plan 04)
    daily connect outlook   -- Connect Microsoft Outlook via OAuth (Plan 05)
"""

import typer

app = typer.Typer(name="daily", help="dAIly - AI personal assistant")
connect_app = typer.Typer(help="Connect integration accounts")
app.add_typer(connect_app, name="connect")


@connect_app.command()
def gmail():
    """Connect Gmail account via Google OAuth."""
    typer.echo("Google OAuth flow not yet implemented (Plan 03)")


@connect_app.command()
def calendar():
    """Connect Google Calendar via Google OAuth."""
    typer.echo("Google OAuth flow not yet implemented (Plan 03)")


@connect_app.command()
def slack():
    """Connect Slack workspace via OAuth."""
    typer.echo("Slack OAuth flow not yet implemented (Plan 04)")


@connect_app.command()
def outlook():
    """Connect Microsoft Outlook via OAuth."""
    typer.echo("Microsoft OAuth flow not yet implemented (Plan 05)")


if __name__ == "__main__":
    app()
