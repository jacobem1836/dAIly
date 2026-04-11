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

async def _upsert_profile(user_id: int, key: str, value: str) -> str:
    """Async helper for profile preference upsert. Called via asyncio.run() from CLI.

    Validates key and value before calling upsert_preference.
    Returns a success or error message string.

    Supported keys: tone, briefing_length, category_order (T-03-09: validated before DB write)
    """
    from daily.db.engine import async_session
    from daily.profile.service import upsert_preference

    valid_keys = {"tone", "briefing_length", "category_order"}
    if key not in valid_keys:
        return f"Unknown profile key: {key}. Valid keys: {', '.join(sorted(valid_keys))}"

    if key == "tone" and value not in ("formal", "casual", "conversational"):
        return f"Invalid tone: {value}. Must be: formal, casual, conversational"
    if key == "briefing_length" and value not in ("concise", "standard", "detailed"):
        return f"Invalid briefing_length: {value}. Must be: concise, standard, detailed"

    async with async_session() as session:
        await upsert_preference(user_id, key, value, session)
        return f"Set profile.{key} = {value}"


async def _get_profile(user_id: int) -> str:
    """Async helper to load and display current profile preferences.

    Returns formatted string of all current preference values.
    Uses defaults if no profile row exists for this user.
    """
    from daily.db.engine import async_session
    from daily.profile.service import load_profile

    async with async_session() as session:
        prefs = await load_profile(user_id, session)
        return (
            f"tone: {prefs.tone}\n"
            f"briefing_length: {prefs.briefing_length}\n"
            f"category_order: {', '.join(prefs.category_order)}"
        )


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
    """Set a briefing or profile config value.

    Keys:
      briefing.schedule_time  -- daily precompute time, format HH:MM (UTC)
      briefing.email_top_n    -- number of top emails to include in briefing
      profile.tone            -- narrative tone: formal, casual, conversational
      profile.briefing_length -- length: concise, standard, detailed
      profile.category_order  -- comma-separated section order (e.g. calendar,emails,slack)

    Examples:
      daily config set briefing.schedule_time 06:00
      daily config set briefing.email_top_n 10
      daily config set profile.tone casual
      daily config set profile.briefing_length detailed
      daily config set profile.category_order calendar,emails,slack
    """
    if key.startswith("profile."):
        profile_key = key.removeprefix("profile.")
        result = asyncio.run(_upsert_profile(user_id=1, key=profile_key, value=value))
        typer.echo(result)
        return
    result = asyncio.run(_upsert_config(user_id=1, key=key, value=value))
    typer.echo(result)


@config_app.command("get")
def config_get(key: str):
    """Get current config values.

    Keys:
      profile  -- show all user profile preferences

    Example:
      daily config get profile
    """
    if key == "profile":
        result = asyncio.run(_get_profile(user_id=1))
        typer.echo(result)
    else:
        typer.echo(f"Unknown get key: {key}. Supported: profile")


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


# ---------------------------------------------------------------------------
# Chat session helpers — module-level imports for testability
# ---------------------------------------------------------------------------
from langgraph.types import Command
from redis.asyncio import Redis

from daily.actions.base import ActionDraft
from daily.db.engine import async_session
from daily.orchestrator.graph import build_graph
from daily.orchestrator.session import (
    create_session_config,
    initialize_session_state,
    run_session,
    set_email_adapters,
)

# ---------------------------------------------------------------------------
# Approval flow helpers
# ---------------------------------------------------------------------------

_SEPARATOR = "-" * 40


def _parse_approval_decision(user_input: str) -> str:
    """Parse user input during an approval prompt into a decision string.

    Decision mapping:
      - confirm/yes/y/send/ok  -> 'confirm'
      - reject/no/n/cancel     -> 'reject'
      - anything else          -> 'edit:{input}' (re-enter draft with edit instruction)

    Args:
        user_input: Raw input string from the user.

    Returns:
        'confirm', 'reject', or 'edit:{instruction}'.
    """
    lowered = user_input.strip().lower()
    if lowered in ("confirm", "yes", "y", "send", "ok"):
        return "confirm"
    if lowered in ("reject", "no", "n", "cancel"):
        return "reject"
    return f"edit:{user_input.strip()}"


def _display_draft_card(draft: ActionDraft) -> None:
    """Display the draft action card in structured format for CLI approval (D-04).

    Format:
        ----------------------------------------
        DRAFT: {action_type}
        ----------------------------------------
        {card_text from ActionDraft}
        ----------------------------------------
        Confirm, reject, or describe changes (e.g. 'make it shorter'):

    Args:
        draft: ActionDraft to display.
    """
    print(_SEPARATOR)
    print(f"DRAFT: {draft.action_type.value}")
    print(_SEPARATOR)
    print(draft.card_text())
    print(_SEPARATOR)
    print("Confirm, reject, or describe changes (e.g. 'make it shorter'):")


def _display_cancellation_message(rejection_behaviour: str = "ask_why") -> None:
    """Display the action cancellation message to the user.

    For both ask_why and discard behaviours, show "Action cancelled."
    ask_why re-entry happens naturally: the user can continue chatting
    to re-enter the draft flow without special prompting.

    Args:
        rejection_behaviour: 'ask_why' or 'discard' from user preferences.
    """
    print("dAIly: Action cancelled.")


async def _handle_approval_flow(
    graph,
    state,
    config: dict,
) -> dict:
    """Handle the approval sub-loop when the graph is interrupted at approval_node.

    Extracts the draft preview from the interrupt payload, displays the card,
    reads user input, parses the decision, and resumes the graph with
    Command(resume=decision).

    For edit decisions (decision.startswith("edit:")):
    - The graph is resumed with the edit decision.
    - The caller (_run_chat_session) should re-invoke the graph with the
      edit instruction as a new user message to trigger another draft pass.

    Args:
        graph: Compiled LangGraph StateGraph with checkpointer.
        state: LangGraph state snapshot with interrupted tasks.
        config: LangGraph config dict with thread_id.

    Returns:
        Dict with 'messages' from the resumed graph, and optionally
        'edit_instruction' if the user requested edits.
    """
    # Extract interrupt payload from the first interrupted task
    preview_text = ""
    action_type_str = "action"

    if state.tasks:
        for task in state.tasks:
            if hasattr(task, "interrupts") and task.interrupts:
                interrupt_value = task.interrupts[0].value
                if isinstance(interrupt_value, dict):
                    preview_text = interrupt_value.get("preview", "")
                    action_type_str = interrupt_value.get("action_type", "action")
                break

    # Display the draft card
    # Build a minimal ActionDraft-like object for display if needed
    # Since we have card_text in the payload, print it directly
    print(_SEPARATOR)
    print(f"DRAFT: {action_type_str}")
    print(_SEPARATOR)
    print(preview_text)
    print(_SEPARATOR)
    print("Confirm, reject, or describe changes (e.g. 'make it shorter'):")

    user_input = input("You: ").strip()
    if not user_input:
        user_input = "reject"

    decision = _parse_approval_decision(user_input)

    # Resume graph with the decision
    result = await graph.ainvoke(Command(resume=decision), config=config)

    # Return result with optional edit instruction for re-entry loop
    output = dict(result) if isinstance(result, dict) else {"messages": []}
    if decision.startswith("edit:"):
        output["edit_instruction"] = decision[len("edit:"):]
    return output


async def _resolve_email_adapters(user_id: int, settings) -> list:
    """Load integration tokens and instantiate real email adapters.

    Follows same pattern as briefing/scheduler.py resolve_pipeline_kwargs.
    Tokens are decrypted in-memory only — never logged (T-03-12).

    Args:
        user_id: User whose integration tokens to load.
        settings: Settings instance providing vault_key.

    Returns:
        List of EmailAdapter instances (GmailAdapter, OutlookAdapter).
        Empty list if no tokens are stored or vault_key is unset.
    """
    from sqlalchemy import select

    from daily.db.engine import async_session
    from daily.db.models import IntegrationToken
    from daily.integrations.google.adapter import GmailAdapter
    from daily.integrations.microsoft.adapter import OutlookAdapter
    from daily.vault.crypto import decrypt_token

    vault_key = base64.b64decode(settings.vault_key) if settings.vault_key else b""
    adapters = []

    async with async_session() as session:
        result = await session.execute(
            select(IntegrationToken).where(IntegrationToken.user_id == user_id)
        )
        tokens = result.scalars().all()

    for token in tokens:
        try:
            decrypted = decrypt_token(token.encrypted_access_token, vault_key)
            if token.provider == "google":
                adapters.append(GmailAdapter(credentials=decrypted))
            elif token.provider == "microsoft":
                adapters.append(OutlookAdapter(credentials=decrypted))
        except Exception:
            # Skip tokens that fail decryption — don't block the session
            pass

    return adapters


async def _run_chat_session(user_id: int = 1) -> None:
    """Async helper for interactive orchestrator chat session.

    Wires real email adapters from stored tokens so BRIEF-07 thread
    summarisation works end-to-end (per D-10). Uses MemorySaver for Phase 3
    CLI; AsyncPostgresSaver will be wired in Phase 5 (FastAPI lifespan).

    Phase 4: Handles approval flow when the graph is interrupted at approval_node.
    Displays the draft card, prompts for confirm/reject/edit, and resumes via
    Command(resume=decision). Edit decisions re-enter the draft loop (D-01).

    Args:
        user_id: User ID for the session. Defaults to 1 (single-user Phase 3).
    """
    from daily.config import Settings

    settings = Settings()

    # 1. Instantiate real email adapters from stored tokens
    adapters = await _resolve_email_adapters(user_id, settings)
    set_email_adapters(adapters)

    # 2. Build graph (MemorySaver for Phase 3 CLI — no Postgres checkpointing yet)
    from langgraph.checkpoint.memory import MemorySaver  # noqa: PLC0415
    graph = build_graph(checkpointer=MemorySaver())

    # 3. Create session config and load initial state from cache + profile
    config = await create_session_config(user_id)
    redis = Redis.from_url(settings.redis_url)
    try:
        async with async_session() as db_sess:
            initial_state = await initialize_session_state(user_id, redis, db_sess)
    finally:
        await redis.aclose()

    # 4. Interactive loop
    print("dAIly chat session started. Type 'exit' or 'quit' to end.")
    if adapters:
        print(f"  {len(adapters)} email adapter(s) connected.")
    else:
        print("  No email adapters connected. Thread summaries won't work.")
        print("  Run 'daily connect gmail' or 'daily connect outlook' first.")
    print()

    first_turn = True
    while True:
        user_input = input("You: ").strip()
        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            print("Session ended.")
            break

        try:
            result = await run_session(
                graph,
                user_input,
                config,
                initial_state=initial_state if first_turn else None,
            )
        except Exception as exc:
            from openai import OpenAIError  # noqa: PLC0415
            if isinstance(exc, OpenAIError):
                print(
                    "Error: OpenAI API key not configured. "
                    "Set OPENAI_API_KEY environment variable to use chat."
                )
                break
            raise
        first_turn = False

        # Check if graph was interrupted (approval gate fired)
        graph_state = await graph.aget_state(config)
        if graph_state.next:
            # Approval interrupt: handle approval sub-loop (D-01 unlimited edit rounds)
            approval_result = await _handle_approval_flow(
                graph=graph,
                state=graph_state,
                config=config,
            )

            # Display result (confirmed or cancelled)
            ap_messages = approval_result.get("messages", [])
            if ap_messages:
                last_msg = ap_messages[-1]
                content = last_msg.content if hasattr(last_msg, "content") else str(last_msg)
                print(f"dAIly: {content}")

            # If edit decision: re-enter loop with edit instruction as new user message (D-01)
            edit_instruction = approval_result.get("edit_instruction")
            if edit_instruction:
                # Automatically send the edit instruction as a new message
                # to re-invoke the draft flow
                try:
                    result = await run_session(graph, edit_instruction, config)
                    # After re-draft, graph will interrupt again — let the loop handle it
                    graph_state2 = await graph.aget_state(config)
                    if graph_state2.next:
                        approval_result2 = await _handle_approval_flow(
                            graph=graph,
                            state=graph_state2,
                            config=config,
                        )
                        ap2_messages = approval_result2.get("messages", [])
                        if ap2_messages:
                            last_msg2 = ap2_messages[-1]
                            content2 = (
                                last_msg2.content
                                if hasattr(last_msg2, "content")
                                else str(last_msg2)
                            )
                            print(f"dAIly: {content2}")
                except Exception:
                    pass
        else:
            # Normal (non-interrupted) response
            messages = result.get("messages", [])
            if messages:
                last_msg = messages[-1]
                content = last_msg.content if hasattr(last_msg, "content") else str(last_msg)
                print(f"dAIly: {content}")
        print()


@app.command()
def chat():
    """Start an interactive chat session with the orchestrator.

    The orchestrator loads your cached briefing and can answer follow-up
    questions. Ask "summarise that email chain" to use BRIEF-07 thread
    summarisation with real email adapters.

    Example:
      daily chat
    """
    asyncio.run(_run_chat_session(user_id=1))


if __name__ == "__main__":
    app()
