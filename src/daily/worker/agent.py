"""LiveKit agent entrypoint — full voice loop over WebRTC.

On dispatch:
  1. Connect to the room.
  2. Resolve user_id from room name (parse_user_id_from_room).
  3. Wait for the participant to publish their mic track (with timeout — T-20.1-08).
  4. Load the user's session bundle (graph + briefing) via load_user_session_state.
  5. Build the VoicePipelineAgent (STT/TTS/VAD/LLM via build_voice_pipeline).
  6. Start the agent against ctx.room.
  7. Speak the briefing as the opening turn (allow_interruptions=True so user can barge in).
  8. VoicePipelineAgent handles the rest of the voice loop until participant leaves.

Note: livekit-agents 0.12.x uses VoicePipelineAgent, not AgentSession (1.0+ API).
"""
import asyncio
import logging

from livekit.agents import JobContext
from livekit.agents.llm import ChatContext

from daily.config import Settings
from daily.worker.identity import parse_user_id_from_room
from daily.worker.llm_bridge import DailyLLMBridge
from daily.worker.state import load_user_session_state
from daily.worker.voice_pipeline import build_voice_pipeline

logger = logging.getLogger(__name__)

# Seconds to wait for a mobile client to join before aborting the job (T-20.1-08).
_PARTICIPANT_TIMEOUT = 300.0

_AGENT_INSTRUCTIONS = (
    "You are dAIly, a personal voice briefing assistant. Be concise and conversational. "
    "Respond in short, natural sentences suitable for spoken delivery."
)


async def entrypoint(ctx: JobContext) -> None:
    await ctx.connect()
    user_id = parse_user_id_from_room(ctx.room.name)
    if user_id is None:
        logger.warning("worker: invalid room name %r — disconnecting", ctx.room.name)
        ctx.shutdown(reason="invalid-room-name")
        return

    logger.info("worker: dispatched room=%s user_id=%d", ctx.room.name, user_id)

    # Wait for the mobile client to publish its mic track before starting the voice loop.
    # Wrap with timeout to prevent the job from hanging forever (T-20.1-08).
    try:
        await asyncio.wait_for(
            ctx.wait_for_participant(),
            timeout=_PARTICIPANT_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "worker: no participant joined within %ss for room=%s — aborting",
            _PARTICIPANT_TIMEOUT,
            ctx.room.name,
        )
        ctx.shutdown(reason="participant-timeout")
        return

    settings = Settings()
    async with load_user_session_state(user_id, settings) as bundle:
        bridge = DailyLLMBridge(
            graph=bundle.graph,
            config=bundle.config,
            initial_state=bundle.initial_state,
        )

        # Seed the chat context with agent instructions.
        chat_ctx = ChatContext()
        chat_ctx.append(role="system", text=_AGENT_INSTRUCTIONS)

        agent = build_voice_pipeline(bridge, settings)
        # Pass chat_ctx to start if supported; start() is synchronous in 0.12.x.
        agent.start(ctx.room)

        # First turn: speak the briefing if we have one.
        briefing = bundle.briefing_narrative
        if briefing:
            logger.info("worker: speaking briefing (%d chars)", len(briefing))
            handle = await agent.say(briefing, allow_interruptions=True)
            await handle.join()
        else:
            logger.info("worker: no cached briefing for user_id=%d", user_id)
            handle = await agent.say(
                "Good morning. I don't have a briefing cached yet — what would you like to talk about?",
                allow_interruptions=True,
            )
            await handle.join()

        # VoicePipelineAgent owns the voice loop from here.
        # Block until the job is shut down (room ends or server signals shutdown).
        done_event = asyncio.Event()

        async def _on_shutdown() -> None:
            done_event.set()

        ctx.add_shutdown_callback(_on_shutdown)
        await done_event.wait()
