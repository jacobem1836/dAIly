"""LangGraph <-> LiveKit Agents LLM adapter.

Wraps `daily.orchestrator.session.astream_session` / `run_session` so the
LiveKit agent can call a single `stream_response(text)` and get an async
iterator of token deltas.

Approval sub-loop: when the graph pauses at approval_node.interrupt() (e.g.
after the user asks to draft/reply to an email), stream_response detects the
interrupt, yields a spoken prompt to the user, and exposes
`pending_approval: bool` so the caller can route the next utterance through
`resume_approval(decision)` instead of a new graph turn.

Historical note: the local CLI voice pipeline (the legacy voice/loop.py module)
implemented an equivalent streaming loop. It was deleted in Phase 21.45 (voice path
consolidation). This module is the sole LLM-to-voice adapter.
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

        # If bridge.pending_approval is True after a turn, the graph is waiting
        # for a confirm/reject decision.  Route the next utterance to:
        async for token in bridge.resume_approval("confirm"):
            print(token, end="", flush=True)
    """

    def __init__(self, graph: object, config: dict, initial_state: dict) -> None:
        self._graph = graph
        self._config = config
        self._initial_state = initial_state
        self._first_turn = True
        # True when the graph is paused at an approval interrupt.
        self.pending_approval: bool = False
        # Briefing narrative stored permanently so follow-up turns retain context.
        # Extracted from initial_state on construction; never cleared after first turn.
        self._briefing_narrative: str = (
            initial_state.get("briefing_narrative", "") if isinstance(initial_state, dict) else ""
        )

    def _extract_last_content(self, result: dict) -> str:
        """Return the content of the last message in a graph result dict."""
        messages = result.get("messages", []) if isinstance(result, dict) else []
        if not messages:
            return ""
        last = messages[-1]
        return last.content if hasattr(last, "content") else str(last)

    def _extract_interrupt_preview(self, graph_state) -> tuple[str, str]:
        """Extract (preview_text, action_type) from a paused graph state.

        Returns ("", "action") if no interrupt payload is found.
        """
        if not graph_state.tasks:
            return "", "action"
        for task in graph_state.tasks:
            if hasattr(task, "interrupts") and task.interrupts:
                value = task.interrupts[0].value
                if isinstance(value, dict):
                    return value.get("preview", ""), value.get("action_type", "action")
        return "", "action"

    async def stream_response(self, user_input: str) -> AsyncIterator[str]:
        """Yield plain-text token deltas for a single user turn.

        Attempts streaming via astream_session for respond-intent turns.
        Falls back to run_session for non-respond intents (summarise/draft/
        approval flows) and yields the final assistant message as a single chunk.

        When the graph pauses at approval_node.interrupt() after an action turn,
        sets self.pending_approval = True and yields a spoken confirmation prompt
        instead of hanging silently.

        First call passes initial_state to the orchestrator; subsequent calls
        pass None (matches the first_turn pattern from voice/loop.py).

        Exit/quit utterances are NOT handled here -- the caller owns those.
        """
        self.pending_approval = False
        init = self._initial_state if self._first_turn else None
        # For streaming respond turns, always inject the briefing narrative so
        # follow-up questions ("tell me more about those emails") have context.
        # astream_session reads briefing_narrative from initial_state only, so
        # we pass a minimal dict with just the narrative on non-first turns.
        stream_init = init if self._first_turn else (
            {"briefing_narrative": self._briefing_narrative} if self._briefing_narrative else None
        )
        try:
            try:
                async for delta in astream_session(self._graph, user_input, self._config, initial_state=stream_init):
                    yield delta
            except StreamingNotSupported:
                logger.debug("llm_bridge: streaming not supported, using run_session")
                result = await run_session(self._graph, user_input, self._config, initial_state=init)

                # Check whether the graph paused at an approval interrupt.
                graph_state = await self._graph.aget_state(self._config)
                if graph_state.next:
                    # Graph is paused -- surface the draft preview via TTS.
                    self.pending_approval = True
                    preview, action_type = self._extract_interrupt_preview(graph_state)
                    if preview:
                        spoken = f"Draft {action_type} ready. {preview}"
                    else:
                        spoken = f"Draft {action_type} ready."
                    yield spoken
                    yield " Say confirm, reject, or describe changes."
                else:
                    content = self._extract_last_content(result)
                    if content:
                        yield content
        finally:
            self._first_turn = False

    async def resume_approval(self, decision: str) -> AsyncIterator[str]:
        """Resume the graph after an approval interrupt with the user's decision.

        Call this when pending_approval is True and the user has spoken their
        confirm/reject/edit response. Resets pending_approval on completion.

        Args:
            decision: One of "confirm", "reject", or "edit: <instruction>".
                      Mirrors _parse_approval_decision() from cli.py.

        Yields:
            Plain-text token deltas of the graph's response after resuming.
        """
        from langgraph.types import Command  # noqa: PLC0415

        self.pending_approval = False
        try:
            result = await self._graph.ainvoke(Command(resume=decision), self._config)
            content = self._extract_last_content(result)

            # Check if graph interrupted again (edit round).
            graph_state = await self._graph.aget_state(self._config)
            if graph_state.next:
                self.pending_approval = True
                preview, action_type = self._extract_interrupt_preview(graph_state)
                if preview:
                    spoken = f"Updated {action_type}. {preview}"
                else:
                    spoken = f"Updated {action_type} ready."
                yield spoken
                yield " Say confirm, reject, or describe further changes."
            else:
                if content:
                    yield content
        except Exception:
            logger.exception("llm_bridge: resume_approval failed")
            yield "Sorry, something went wrong resuming the action."
