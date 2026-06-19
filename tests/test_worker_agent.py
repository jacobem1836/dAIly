"""Tests for daily.worker.agent entrypoint — invalid room and timeout paths."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_entrypoint_invalid_room_name():
    """entrypoint shuts down immediately when room name cannot be parsed."""
    from daily.worker.agent import entrypoint

    mock_ctx = AsyncMock()
    mock_ctx.room = MagicMock()
    mock_ctx.room.name = "invalid-room-name-no-user"
    mock_ctx.connect = AsyncMock()
    mock_ctx.shutdown = MagicMock()

    with patch("daily.worker.agent.parse_user_id_from_room", return_value=None):
        await entrypoint(mock_ctx)

    mock_ctx.connect.assert_called_once()
    mock_ctx.shutdown.assert_called_once_with(reason="invalid-room-name")


@pytest.mark.asyncio
async def test_entrypoint_participant_timeout():
    """entrypoint shuts down with 'participant-timeout' when wait_for_participant times out."""
    from daily.worker.agent import entrypoint

    mock_ctx = AsyncMock()
    mock_ctx.room = MagicMock()
    mock_ctx.room.name = "briefing_user_42"
    mock_ctx.connect = AsyncMock()
    mock_ctx.shutdown = MagicMock()

    async def _timeout_coroutine():
        raise asyncio.TimeoutError()

    mock_ctx.wait_for_participant = AsyncMock(side_effect=asyncio.TimeoutError())

    with (
        patch("daily.worker.agent.parse_user_id_from_room", return_value=42),
        patch("asyncio.wait_for", side_effect=asyncio.TimeoutError()),
    ):
        await entrypoint(mock_ctx)

    mock_ctx.shutdown.assert_called_once_with(reason="participant-timeout")
