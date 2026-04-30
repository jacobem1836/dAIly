"""LiveKit agent entrypoint. Per-room handler — full voice logic added in Plan 20.1-02."""
import logging

from livekit.agents import JobContext

from daily.worker.identity import parse_user_id_from_room

logger = logging.getLogger(__name__)


async def entrypoint(ctx: JobContext) -> None:
    """Called by the LiveKit Agents framework once per dispatched job.

    Plan 20.1-01 scope: connect to the room, log identity, exit cleanly.
    Plan 20.1-02 will replace this body with the briefing + voice loop.
    """
    await ctx.connect()
    user_id = parse_user_id_from_room(ctx.room.name)
    if user_id is None:
        logger.warning("worker: room name %r did not match session-{uid}-{ts}; disconnecting", ctx.room.name)
        await ctx.shutdown(reason="invalid-room-name")
        return
    logger.info("worker: connected to room=%s user_id=%d", ctx.room.name, user_id)
    # Hold the job open until the room ends (filled out in Plan 20.1-02).
    await ctx.wait_for_participant()
