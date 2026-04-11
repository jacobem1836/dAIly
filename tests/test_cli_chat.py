"""Tests for the CLI `daily chat` command (Task 3 TDD).

Tests cover:
- `chat` command is registered on the Typer app
- Adapter registry is populated before graph runs
- Session config uses correct thread_id pattern
- Interactive loop handles input and exit
- set_email_adapters is called with resolved adapters
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage
from typer.testing import CliRunner


runner = CliRunner()


def _make_mock_graph():
    """Create a mock graph that returns a canned response."""
    mock_graph = AsyncMock()
    mock_graph.ainvoke = AsyncMock(return_value={
        "messages": [AIMessage(content="You have 3 important emails today.")]
    })
    mock_graph.checkpointer = MagicMock()

    # Return a non-interrupted state (next=[]) so the approval flow is not triggered
    mock_state = MagicMock()
    mock_state.next = []
    mock_state.tasks = []
    mock_graph.aget_state = AsyncMock(return_value=mock_state)

    return mock_graph


class TestChatCommandRegistered:
    def test_chat_command_exists_on_app(self):
        """The `chat` command is registered on the daily Typer app.

        Uses --help output to verify registration since Typer stores @app.command()
        decorated functions with None name in registered_commands (name is derived
        from the function at CLI invocation time).
        """
        from daily.cli import app

        result = runner.invoke(app, ["--help"])
        assert "chat" in result.output

    def test_chat_command_is_callable_via_runner(self):
        """CLI runner can invoke `daily chat` without crashing on missing infra."""
        from daily.cli import app

        # We'll patch the entire _run_chat_session to avoid real DB/Redis calls
        with patch("daily.cli._run_chat_session", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = None
            result = runner.invoke(app, ["chat"])

        # Should have invoked _run_chat_session
        mock_run.assert_called_once()


class TestChatAdapterWiring:
    def test_set_email_adapters_called_before_graph_runs(self):
        """chat command calls set_email_adapters with resolved adapters before graph invocation."""
        from daily.cli import app

        mock_adapter = MagicMock()
        call_order = []

        async def mock_resolve(user_id, settings):
            call_order.append("resolve")
            return [mock_adapter]

        async def mock_set_adapters(adapters):
            # set_email_adapters is synchronous — just track the call
            pass

        with patch("daily.cli._resolve_email_adapters", side_effect=mock_resolve):
            with patch("daily.cli.set_email_adapters") as mock_set:
                mock_set.side_effect = lambda a: call_order.append("set")

                with patch("daily.cli.build_graph") as mock_build:
                    mock_graph = _make_mock_graph()
                    mock_build.return_value = mock_graph

                    with patch("daily.cli.create_session_config", new_callable=AsyncMock) as mock_cfg:
                        mock_cfg.return_value = {"configurable": {"thread_id": "user-1-2026-04-07"}}

                        with patch("daily.cli.initialize_session_state", new_callable=AsyncMock) as mock_init:
                            mock_init.return_value = {"briefing_narrative": ""}

                            with patch("daily.cli.run_session", new_callable=AsyncMock) as mock_run:
                                mock_run.return_value = {"messages": [AIMessage(content="Hi!")]}

                                with patch("daily.cli.Redis", _mock_redis()[0]):
                                    with patch("daily.cli.async_session", _mock_async_session_ctx()):
                                        result = runner.invoke(app, ["chat"], input="exit\n")

        # Resolve should happen before set
        assert "resolve" in call_order
        assert "set" in call_order
        resolve_idx = call_order.index("resolve")
        set_idx = call_order.index("set")
        assert resolve_idx < set_idx

    def test_set_email_adapters_called_with_resolved_adapters(self):
        """set_email_adapters receives the adapters from _resolve_email_adapters."""
        from daily.cli import app

        mock_adapter = MagicMock()
        captured_adapters = []

        async def mock_resolve(user_id, settings):
            return [mock_adapter]

        with patch("daily.cli._resolve_email_adapters", side_effect=mock_resolve):
            with patch("daily.cli.set_email_adapters") as mock_set:
                mock_set.side_effect = lambda a: captured_adapters.extend(a)

                with patch("daily.cli.build_graph") as mock_build:
                    mock_graph = _make_mock_graph()
                    mock_build.return_value = mock_graph

                    with patch("daily.cli.create_session_config", new_callable=AsyncMock) as mock_cfg:
                        mock_cfg.return_value = {"configurable": {"thread_id": "user-1-2026-04-07"}}

                        with patch("daily.cli.initialize_session_state", new_callable=AsyncMock) as mock_init:
                            mock_init.return_value = {}

                            with patch("daily.cli.run_session", new_callable=AsyncMock) as mock_run:
                                mock_run.return_value = {"messages": [AIMessage(content="Hi!")]}

                                with patch("daily.cli.Redis", _mock_redis()[0]):
                                    with patch("daily.cli.async_session", _mock_async_session_ctx()):
                                        runner.invoke(app, ["chat"], input="exit\n")

        assert mock_adapter in captured_adapters


class TestChatSessionConfig:
    def test_chat_uses_user_date_thread_id_pattern(self):
        """Chat session creates config with user-{id}-{date} thread_id pattern."""
        from daily.cli import app

        captured_configs = []

        async def mock_create_config(user_id, session_date=None):
            config = {"configurable": {"thread_id": f"user-{user_id}-2026-04-07"}}
            captured_configs.append(config)
            return config

        with patch("daily.cli._resolve_email_adapters", new_callable=AsyncMock) as mock_resolve:
            mock_resolve.return_value = []

            with patch("daily.cli.set_email_adapters"):
                with patch("daily.cli.build_graph") as mock_build:
                    mock_graph = _make_mock_graph()
                    mock_build.return_value = mock_graph

                    with patch("daily.cli.create_session_config", side_effect=mock_create_config):
                        with patch("daily.cli.initialize_session_state", new_callable=AsyncMock) as mock_init:
                            mock_init.return_value = {}

                            with patch("daily.cli.run_session", new_callable=AsyncMock) as mock_run:
                                mock_run.return_value = {"messages": [AIMessage(content="Hi!")]}

                                with patch("daily.cli.Redis", _mock_redis()[0]):
                                    with patch("daily.cli.async_session", _mock_async_session_ctx()):
                                        runner.invoke(app, ["chat"], input="exit\n")

        assert len(captured_configs) == 1
        thread_id = captured_configs[0]["configurable"]["thread_id"]
        assert thread_id.startswith("user-1-")


def _mock_redis():
    """Create a properly async-mocked Redis for CLI tests."""
    mock_redis_instance = AsyncMock()
    mock_redis_instance.aclose = AsyncMock()
    mock_redis_class = MagicMock()
    mock_redis_class.from_url = MagicMock(return_value=mock_redis_instance)
    return mock_redis_class, mock_redis_instance


def _mock_async_session_ctx():
    """Create a properly mocked async_session context manager."""
    mock_session = AsyncMock()
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_async_session = MagicMock(return_value=mock_ctx)
    return mock_async_session


class TestChatInteractiveLoop:
    def test_chat_exits_on_exit_command(self):
        """Typing 'exit' ends the chat session cleanly."""
        from daily.cli import app

        mock_redis_class, _ = _mock_redis()
        mock_async_session = _mock_async_session_ctx()

        with patch("daily.cli._resolve_email_adapters", new_callable=AsyncMock) as mock_resolve:
            mock_resolve.return_value = []

            with patch("daily.cli.set_email_adapters"):
                with patch("daily.cli.build_graph") as mock_build:
                    mock_graph = _make_mock_graph()
                    mock_build.return_value = mock_graph

                    with patch("daily.cli.create_session_config", new_callable=AsyncMock) as mock_cfg:
                        mock_cfg.return_value = {"configurable": {"thread_id": "user-1-2026-04-07"}}

                        with patch("daily.cli.initialize_session_state", new_callable=AsyncMock) as mock_init:
                            mock_init.return_value = {}

                            with patch("daily.cli.run_session", new_callable=AsyncMock) as mock_run:
                                mock_run.return_value = {"messages": []}

                                with patch("daily.cli.Redis", mock_redis_class):
                                    with patch("daily.cli.async_session", mock_async_session):
                                        result = runner.invoke(app, ["chat"], input="exit\n")

        assert result.exit_code == 0

    def test_chat_exits_on_quit_command(self):
        """Typing 'quit' also ends the chat session."""
        from daily.cli import app

        mock_redis_class, _ = _mock_redis()
        mock_async_session = _mock_async_session_ctx()

        with patch("daily.cli._resolve_email_adapters", new_callable=AsyncMock) as mock_resolve:
            mock_resolve.return_value = []

            with patch("daily.cli.set_email_adapters"):
                with patch("daily.cli.build_graph") as mock_build:
                    mock_graph = _make_mock_graph()
                    mock_build.return_value = mock_graph

                    with patch("daily.cli.create_session_config", new_callable=AsyncMock) as mock_cfg:
                        mock_cfg.return_value = {"configurable": {"thread_id": "user-1-2026-04-07"}}

                        with patch("daily.cli.initialize_session_state", new_callable=AsyncMock) as mock_init:
                            mock_init.return_value = {}

                            with patch("daily.cli.run_session", new_callable=AsyncMock) as mock_run:
                                mock_run.return_value = {"messages": []}

                                with patch("daily.cli.Redis", mock_redis_class):
                                    with patch("daily.cli.async_session", mock_async_session):
                                        result = runner.invoke(app, ["chat"], input="quit\n")

        assert result.exit_code == 0

    def test_chat_calls_run_session_with_user_input(self):
        """Chat loop calls run_session with user input text."""
        from daily.cli import app

        captured_inputs = []
        mock_redis_class, _ = _mock_redis()
        mock_async_session = _mock_async_session_ctx()

        async def mock_run_session(graph, user_input, config, initial_state=None):
            captured_inputs.append(user_input)
            return {"messages": [AIMessage(content="Response.")]}

        with patch("daily.cli._resolve_email_adapters", new_callable=AsyncMock) as mock_resolve:
            mock_resolve.return_value = []

            with patch("daily.cli.set_email_adapters"):
                with patch("daily.cli.build_graph") as mock_build:
                    mock_graph = _make_mock_graph()
                    mock_build.return_value = mock_graph

                    with patch("daily.cli.create_session_config", new_callable=AsyncMock) as mock_cfg:
                        mock_cfg.return_value = {"configurable": {"thread_id": "user-1-2026-04-07"}}

                        with patch("daily.cli.initialize_session_state", new_callable=AsyncMock) as mock_init:
                            mock_init.return_value = {}

                            with patch("daily.cli.run_session", side_effect=mock_run_session):
                                with patch("daily.cli.Redis", mock_redis_class):
                                    with patch("daily.cli.async_session", mock_async_session):
                                        runner.invoke(app, ["chat"], input="tell me about my emails\nexit\n")

        assert "tell me about my emails" in captured_inputs

    def test_chat_prints_ai_response(self):
        """Chat loop prints the AI response message to stdout."""
        from daily.cli import app

        mock_redis_class, _ = _mock_redis()
        mock_async_session = _mock_async_session_ctx()

        with patch("daily.cli._resolve_email_adapters", new_callable=AsyncMock) as mock_resolve:
            mock_resolve.return_value = []

            with patch("daily.cli.set_email_adapters"):
                with patch("daily.cli.build_graph") as mock_build:
                    mock_graph = _make_mock_graph()
                    mock_build.return_value = mock_graph

                    with patch("daily.cli.create_session_config", new_callable=AsyncMock) as mock_cfg:
                        mock_cfg.return_value = {"configurable": {"thread_id": "user-1-2026-04-07"}}

                        with patch("daily.cli.initialize_session_state", new_callable=AsyncMock) as mock_init:
                            mock_init.return_value = {}

                            with patch("daily.cli.run_session", new_callable=AsyncMock) as mock_run:
                                mock_run.return_value = {
                                    "messages": [AIMessage(content="You have 3 emails today.")]
                                }

                                with patch("daily.cli.Redis", mock_redis_class):
                                    with patch("daily.cli.async_session", mock_async_session):
                                        result = runner.invoke(app, ["chat"], input="what emails\nexit\n")

        assert "You have 3 emails today." in result.output


class TestResolveEmailAdapters:
    def test_resolve_email_adapters_function_exists(self):
        """_resolve_email_adapters function exists in cli.py."""
        from daily.cli import _resolve_email_adapters
        import asyncio
        assert asyncio.iscoroutinefunction(_resolve_email_adapters)
