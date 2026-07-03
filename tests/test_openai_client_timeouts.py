"""Regression tests for audit H7: OpenAI clients built without timeout/retries.

Without an explicit timeout/max_retries, the OpenAI SDK's own (very long)
defaults apply, so a slow or transiently-failing call could hang a request
or a scheduled run far longer than acceptable. Every AsyncOpenAI(...)
construction site in the codebase must pass explicit timeout and
max_retries kwargs.
"""
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_scheduler_openai_client_has_timeout_and_retries(monkeypatch):
    """_build_pipeline_kwargs constructs AsyncOpenAI with timeout + max_retries."""
    from unittest.mock import AsyncMock

    from daily.briefing.scheduler import (
        OPENAI_CLIENT_MAX_RETRIES,
        OPENAI_CLIENT_TIMEOUT_SECONDS,
        _build_pipeline_kwargs,
    )
    from daily.config import Settings

    mock_session = AsyncMock()
    mock_result_vip = MagicMock()
    mock_result_vip.fetchall.return_value = []
    mock_result_tokens = MagicMock()
    mock_result_tokens.scalars.return_value.all.return_value = []
    mock_result_config = MagicMock()
    mock_result_config.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(
        side_effect=[mock_result_vip, mock_result_tokens, mock_result_config]
    )
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("daily.briefing.scheduler.async_session", return_value=mock_ctx),
        patch("daily.briefing.scheduler.load_profile", new=AsyncMock(return_value={})),
        patch("daily.briefing.scheduler.AsyncOpenAI") as mock_openai_cls,
    ):
        settings = Settings(
            redis_url="redis://localhost:6379/0",
            openai_api_key="test-key",
            briefing_email_top_n=5,
        )
        await _build_pipeline_kwargs(user_id=1, settings=settings)

    mock_openai_cls.assert_called_once()
    call_kwargs = mock_openai_cls.call_args.kwargs
    assert call_kwargs["timeout"] == OPENAI_CLIENT_TIMEOUT_SECONDS
    assert call_kwargs["max_retries"] == OPENAI_CLIENT_MAX_RETRIES


def test_orchestrator_session_openai_client_has_timeout_and_retries(monkeypatch):
    """orchestrator.session._get_openai_client constructs AsyncOpenAI with timeout + max_retries."""
    import daily.orchestrator.session as session_module

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(session_module, "_openai_client", None)

    with patch("daily.orchestrator.session.AsyncOpenAI") as mock_openai_cls:
        session_module._get_openai_client()

    mock_openai_cls.assert_called_once()
    call_kwargs = mock_openai_cls.call_args.kwargs
    assert call_kwargs["timeout"] == session_module._OPENAI_CLIENT_TIMEOUT_SECONDS
    assert call_kwargs["max_retries"] == session_module._OPENAI_CLIENT_MAX_RETRIES

    # Reset the module-level cache so this test doesn't leak a MagicMock
    # client into other tests that import the same module.
    monkeypatch.setattr(session_module, "_openai_client", None)


def test_orchestrator_nodes_openai_client_has_timeout_and_retries(monkeypatch):
    """orchestrator.nodes._openai_client constructs AsyncOpenAI with timeout + max_retries."""
    import daily.orchestrator.nodes as nodes_module

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    with patch("daily.orchestrator.nodes.AsyncOpenAI") as mock_openai_cls:
        nodes_module._openai_client()

    mock_openai_cls.assert_called_once()
    call_kwargs = mock_openai_cls.call_args.kwargs
    assert call_kwargs["timeout"] == nodes_module._OPENAI_CLIENT_TIMEOUT_SECONDS
    assert call_kwargs["max_retries"] == nodes_module._OPENAI_CLIENT_MAX_RETRIES
