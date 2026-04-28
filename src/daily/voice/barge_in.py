"""Barge-in coordination layer: asyncio task management for TTS/STT concurrency.

Implements VoiceTurnManager which coordinates TTSPipeline and STTPipeline with
a shared asyncio.Event stop flag, TTS task cancellation, and echo suppression.

Design decisions:
- D-03: asyncio.Event stop flag shared between TTS and STT tasks
- D-04: stop_event is checked between every audio chunk (enforced by TTSPipeline)
- Barge-in uses a 600ms safety window (asyncio timer) to prevent noise/cough interrupts
- Backchannel detection suppresses "yeah"/"ok"/etc from triggering barge-in during TTS
- T-05-08: Echo suppression flag prevents self-triggering DoS from rapid speech_started
"""
import asyncio

from daily.voice.stt import STTPipeline
from daily.voice.tts import TTSPipeline
from daily.voice.utils import _is_backchannel


class VoiceTurnManager:
    """Coordinates TTS/STT concurrency with barge-in detection.

    Per D-03: asyncio.Event stop flag shared between TTS and STT.
    Per D-04: TTS checks stop_event between every chunk (enforced by TTSPipeline).
    Barge-in uses a 600ms deferred timer so brief noises / coughs do not interrupt.
    Backchannel utterances ("yeah", "ok", etc.) during TTS are swallowed so TTS continues.

    Usage::

        tts = TTSPipeline(api_key=settings.cartesia_api_key)
        stt = STTPipeline(api_key=settings.deepgram_api_key)
        manager = VoiceTurnManager(tts=tts, stt=stt)

        listen_stop = asyncio.Event()
        await manager.start_stt(listen_stop)

        completed = await manager.speak("Good morning. Here is your briefing.")
        if not completed:
            # User interrupted — wait for their utterance
            utterance = await manager.wait_for_utterance()

        await manager.stop()
    """

    def __init__(self, tts: TTSPipeline, stt: STTPipeline) -> None:
        self._tts = tts
        self._stt = stt
        self._stop_event: asyncio.Event = asyncio.Event()
        self._tts_active: bool = False
        self._tts_task: asyncio.Task | None = None
        self._stt_task: asyncio.Task | None = None
        self._unmute_task: asyncio.Task | None = None
        # Barge-in timer fields (Plan 17-03)
        self._pending_barge_in_cancelled: bool = False
        self._barge_in_timer_task: asyncio.Task | None = None
        self._was_tts_active_at_speech_start: bool = False

    # ------------------------------------------------------------------
    # Echo suppression — delayed unmute
    # ------------------------------------------------------------------

    async def _unmute_after_delay(self) -> None:
        """Unmute the STT mic after a 500ms delay.

        The delay matches the barge-in safety window: TTS audio takes ~200–400ms
        to fully leave the speakers before Deepgram could mistakenly detect it as
        speech. Waiting 500ms ensures any trailing echo has subsided so a genuine
        user interrupt (barge-in) can still be detected.

        If cancelled before the delay elapses (e.g. TTS finished early and the
        finally block cancelled this task), unmute immediately so the mic is never
        left muted on any exit path.
        """
        try:
            await asyncio.sleep(0.5)
            self._stt.muted = False
        except asyncio.CancelledError:
            # Cancelled because TTS finished early — ensure unmute regardless
            self._stt.muted = False
            raise

    # ------------------------------------------------------------------
    # Barge-in callback + 600ms safety window timer
    # ------------------------------------------------------------------

    def _on_speech_started(self) -> None:
        """Called by STTPipeline when Deepgram detects speech onset.

        Captures TTS state at onset time (UtteranceEnd arrives ~1000ms later by
        which time _tts_active may already be False). Schedules a 600ms timer
        that sets stop_event only if not cancelled by then (e.g. by filter_utterance
        detecting a backchannel, or by speak() starting a new turn).

        The 600ms window prevents brief noise/cough events from interrupting TTS.
        """
        # Capture TTS state at the moment speech started — UtteranceEnd will not
        # arrive for ~1000ms, by which time _tts_active may already be False.
        self._was_tts_active_at_speech_start = self._tts_active
        self._pending_barge_in_cancelled = False
        # Cancel any prior pending timer (defensive — should not happen in practice)
        if self._barge_in_timer_task is not None and not self._barge_in_timer_task.done():
            self._barge_in_timer_task.cancel()
        self._barge_in_timer_task = asyncio.create_task(
            self._commit_barge_in_after_window()
        )

    async def _commit_barge_in_after_window(self) -> None:
        """Fire stop_event after a 600ms safety window, unless cancelled."""
        try:
            await asyncio.sleep(0.6)
        except asyncio.CancelledError:
            return
        if not self._pending_barge_in_cancelled:
            self._stop_event.set()

    # ------------------------------------------------------------------
    # Backchannel filter
    # ------------------------------------------------------------------

    def filter_utterance(self, text: str) -> bool:
        """Return True to forward the utterance, False to swallow it.

        A backchannel is swallowed when TTS was active at the moment speech
        started. Cancels the pending barge-in timer so TTS keeps going.

        Args:
            text: Transcript from Deepgram UtteranceEnd.

        Returns:
            True if utterance should be forwarded to the orchestrator.
            False if it is a backchannel that should be suppressed.
        """
        if self._was_tts_active_at_speech_start and _is_backchannel(text):
            self._pending_barge_in_cancelled = True
            if self._barge_in_timer_task is not None and not self._barge_in_timer_task.done():
                self._barge_in_timer_task.cancel()
            return False
        return True

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def speak(self, text: str) -> bool:
        """Play TTS audio with barge-in support.

        Sets tts_active=True during playback. Clears stop_event before starting
        and in finally block after. Cancels any in-flight barge-in timer from
        a prior turn so it cannot fire into this turn's clear/set cycle.

        Args:
            text: The text to convert to speech and play.

        Returns:
            True if playback completed normally.
            False if interrupted by barge-in (stop_event was set).
        """
        # Cancel any in-flight barge-in timer left from a previous turn
        if self._barge_in_timer_task is not None and not self._barge_in_timer_task.done():
            self._barge_in_timer_task.cancel()
        self._barge_in_timer_task = None
        self._pending_barge_in_cancelled = False
        self._was_tts_active_at_speech_start = False

        self._stop_event.clear()
        self._tts_active = True
        self._stt.muted = True  # Mute mic to prevent echo feedback loop
        self._unmute_task = asyncio.create_task(self._unmute_after_delay())
        self._stt._transcript_parts.clear()  # Discard any in-flight echo fragments
        interrupted = False
        try:
            self._tts_task = asyncio.create_task(
                self._tts.play_streaming(text, self._stop_event)
            )
            await self._tts_task
        except asyncio.CancelledError:
            interrupted = True
        else:
            # Check if stop_event was set (barge-in path via stop_event.set)
            if self._stop_event.is_set():
                interrupted = True
        finally:
            self._tts_active = False
            if self._unmute_task is not None and not self._unmute_task.done():
                self._unmute_task.cancel()
            self._unmute_task = None
            self._stt.muted = False  # Belt and braces: ensure unmuted on every exit
            self._stt._transcript_parts.clear()  # Discard any trailing echo
            self._was_tts_active_at_speech_start = False
            self._stop_event.clear()
            self._tts_task = None

        return not interrupted

    async def wait_for_utterance(self) -> str:
        """Block until STTPipeline emits a complete utterance via UtteranceEnd.

        Returns:
            The transcript string from the STT pipeline's utterance_queue.
        """
        return await self._stt.utterance_queue.get()

    async def start_stt(self, listen_stop: asyncio.Event) -> None:
        """Start the STT listener as a background task.

        Wires self._on_speech_started as the STT's speech-started callback
        so that Deepgram SpeechStarted events propagate to barge-in logic.

        Args:
            listen_stop: Set this event to stop the STT listener.
        """
        # Wire barge-in callback into STT pipeline
        self._stt._on_speech_started = self._on_speech_started
        self._stt_task = asyncio.create_task(self._stt.start_listening(listen_stop))

    async def stop(self) -> None:
        """Clean shutdown of TTS and STT resources.

        Cancels in-flight TTS task (triggers barge-in path in speak()).
        Cancels STT listener task. Cancels any pending barge-in timer.
        """
        # Cancel barge-in timer before other cleanup
        if self._barge_in_timer_task is not None and not self._barge_in_timer_task.done():
            self._barge_in_timer_task.cancel()
        self._barge_in_timer_task = None
        self._pending_barge_in_cancelled = True

        if self._unmute_task is not None and not self._unmute_task.done():
            self._unmute_task.cancel()
        self._stt.muted = False

        if self._tts_task is not None and not self._tts_task.done():
            self._stop_event.set()
            self._tts_task.cancel()
            try:
                await self._tts_task
            except (asyncio.CancelledError, Exception):
                pass

        if self._stt_task is not None and not self._stt_task.done():
            self._stt_task.cancel()
            try:
                await self._stt_task
            except (asyncio.CancelledError, Exception):
                pass
