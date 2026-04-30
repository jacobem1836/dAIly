"""LiveKit VoicePipelineAgent factory wiring Deepgram STT, Cartesia TTS, Silero VAD,
and our LangGraph-backed DailyLLMBridge.

Note: livekit-agents 0.12.x uses VoicePipelineAgent (not AgentSession).
AgentSession was introduced in livekit-agents 1.0+.
"""
import logging
from typing import AsyncIterator

from livekit.agents import APIConnectOptions
from livekit.agents import llm as agents_llm
from livekit.agents.pipeline import VoicePipelineAgent
from livekit.plugins import cartesia, deepgram, silero

from daily.config import Settings
from daily.worker.llm_bridge import DailyLLMBridge

logger = logging.getLogger(__name__)

# Match the Cartesia voice used in the existing TTS pipeline (voice/tts.py).
_DEFAULT_VOICE_ID = "6ccbfb76-1fc6-48f7-b71d-91ac6298247b"

_CONNECT_OPTIONS = APIConnectOptions(max_retry=2, retry_interval=1.0, timeout=15.0)


class DailyAgentLLM(agents_llm.LLM):
    """Adapter exposing DailyLLMBridge as a livekit-agents LLM.

    Implements the LLM base class required by VoicePipelineAgent.
    Extracts the most recent user message from the chat context and
    routes it through DailyLLMBridge.stream_response().
    """

    def __init__(self, bridge: DailyLLMBridge) -> None:
        super().__init__()
        self._bridge = bridge

    def chat(
        self,
        *,
        chat_ctx: agents_llm.ChatContext,
        conn_options: APIConnectOptions = _CONNECT_OPTIONS,
        fnc_ctx: "agents_llm.function_context.FunctionContext | None" = None,
        **kwargs: object,
    ) -> "_DailyLLMStream":
        # Extract the most recent user message from the chat context.
        user_msg = ""
        for msg in reversed(chat_ctx.messages):
            if getattr(msg, "role", None) == "user":
                content = msg.content
                user_msg = content if isinstance(content, str) else str(content) if content is not None else ""
                break
        return _DailyLLMStream(
            self,
            chat_ctx=chat_ctx,
            fnc_ctx=fnc_ctx,
            conn_options=conn_options,
            bridge=self._bridge,
            user_msg=user_msg,
        )


class _DailyLLMStream(agents_llm.LLMStream):
    def __init__(
        self,
        llm: DailyAgentLLM,
        *,
        chat_ctx: agents_llm.ChatContext,
        fnc_ctx: "agents_llm.function_context.FunctionContext | None",
        conn_options: APIConnectOptions,
        bridge: DailyLLMBridge,
        user_msg: str,
    ) -> None:
        super().__init__(llm=llm, chat_ctx=chat_ctx, fnc_ctx=fnc_ctx, conn_options=conn_options)
        self._bridge = bridge
        self._user_msg = user_msg

    async def _run(self) -> None:
        async for delta in self._bridge.stream_response(self._user_msg):
            chunk = agents_llm.ChatChunk(
                request_id="",
                choices=[
                    agents_llm.Choice(
                        delta=agents_llm.ChoiceDelta(role="assistant", content=delta),
                        index=0,
                    )
                ],
            )
            self._event_ch.send_nowait(chunk)


def build_voice_pipeline(bridge: DailyLLMBridge, settings: Settings) -> VoicePipelineAgent:
    """Construct a VoicePipelineAgent ready to .start() against a JobContext.room.

    Wires:
    - Deepgram Nova-3 STT (streaming, en-US)
    - Cartesia TTS with the project-standard voice ID
    - Silero VAD for end-of-utterance detection
    - DailyAgentLLM adapter routing turns to DailyLLMBridge
    """
    return VoicePipelineAgent(
        stt=deepgram.STT(model="nova-3", api_key=settings.deepgram_api_key),
        tts=cartesia.TTS(
            model="sonic-2",
            voice=_DEFAULT_VOICE_ID,
            api_key=settings.cartesia_api_key,
        ),
        vad=silero.VAD.load(),
        llm=DailyAgentLLM(bridge),
    )
