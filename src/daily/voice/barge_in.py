"""Barge-in coordination layer: asyncio task management for TTS/STT concurrency.

Implements VoiceTurnManager which coordinates TTSPipeline and STTPipeline with
a shared asyncio.Event stop flag, TTS task cancellation, and echo suppression.

Design decisions:
- D-03: asyncio.Event stop flag shared between TTS and STT tasks
- D-04: stop_event is checked between every audio chunk (enforced by TTSPipeline)
- Pitfall 6: tts_active flag suppresses speech_started during TTS playback to prevent
  TTS audio from triggering its own barge-in (echo suppression)
- T-05-08: Echo suppression flag prevents self-triggering DoS from rapid speech_started
"""
import asyncio

from daily.voice.stt import STTPipeline
from daily.voice.tts import TTSPipeline


class VoiceTurnManager:
    """Coordinates TTS/STT concurrency with barge-in detection.

    Per D-03: asyncio.Event stop flag shared between TTS and STT.
    Per D-04: TTS checks stop_event between every chunk (enforced by TTSPipeline).
    Per Pitfall 6: tts_active flag suppresses speech_started during playback.

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
    # Barge-in callback
    # ------------------------------------------------------------------

    def _on_speech_started(self) -> None:
        """Called by STTPipeline when Deepgram detects speech onset.

        Per Pitfall 6: If TTS is currently playing, suppress the barge-in
        to avoid echo-triggered self-interruption. Only set stop_event
        when TTS is NOT active (real user speech).

        T-05-08: stop_event.set() is idempotent — rapid speech_started
        events are safe and do not cause a DoS loop.
        """
        if not self._tts_active:
            self._stop_event.set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def speak(self, text: str) -> bool:
        """Play TTS audio with barge-in support.

        Sets tts_active=True during playback (suppresses echo barge-in).
        Clears stop_event before starting and in finally block after.

        Args:
            text: The text to convert to speech and play.

        Returns:
            True if playback completed normally.
            False if interrupted by barge-in (stop_event was set).
        """
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
        Cancels STT listener task.
        """
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
