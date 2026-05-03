"""LangGraph <-> LiveKit Agents LLM adapter.

Wraps `daily.orchestrator.session.astream_session` / `run_session` so the
LiveKit agent can call a single `stream_response(text)` and get an async
iterator of token deltas — same streaming pattern as
`daily.voice.loop.run_voice_session` lines 222–286.
"""
import logging
from collections.abc import AsyncIterator

from daily.orchestrator.session import (
    StreamingNotSupported,
    astream_session,
    run_session,
)

logger = logging.getLogger(__name__)


class DailyLLMBridge:
    """Adapter from user text to streaming LLM tokens via LangGraph.

    Usage:
        bridge = DailyLLMBridge(graph=graph, config=config, initial_state=initial_state)
        async for token in bridge.stream_response("what's on my calendar?"):
            print(token, end="", flush=True)
    """

    def __init__(self, graph: object, config: dict, initial_state: dict) -> None:
        self._graph = graph
        self._config = config
        self._initial_state = initial_state
        self._first_turn = True

    async def stream_response(self, user_input: str) -> AsyncIterator[str]:
        """Yield plain-text token deltas for a single user turn.

        Attempts streaming via astream_session for respond-intent turns.
        Falls back to run_session for non-respond intents (summarise/draft/
        approval flows) and yields the final assistant message as a single chunk.

        First call passes initial_state to the orchestrator; subsequent calls
        pass None (matches the first_turn pattern from voice/loop.py).

        Exit/quit utterances are NOT handled here — the caller owns those.
        """
        init = self._initial_state if self._first_turn else None
        try:
            async for delta in astream_session(self._graph, user_input, self._config, initial_state=init):
                yield delta
        except StreamingNotSupported:
            logger.debug("llm_bridge: streaming not supported, using run_session")
            result = await run_session(self._graph, user_input, self._config, initial_state=init)
            messages = result.get("messages", []) if isinstance(result, dict) else []
            if messages:
                last = messages[-1]
                content = last.content if hasattr(last, "content") else str(last)
                yield content
        finally:
            self._first_turn = False
