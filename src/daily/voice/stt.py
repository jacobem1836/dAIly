"""STT pipeline: Deepgram Nova-3 WebSocket streaming with sounddevice mic capture.

Implements:
- D-09: Deepgram Nova-3 via WebSocket SDK with interim results for low-latency display.
- D-05: Deepgram built-in VAD only (no Silero). Uses UtteranceEnd + speech_started events.
- D-06: UtteranceEnd fires -> accumulated final transcript sent to orchestrator via utterance_queue.
- D-10: Interim transcripts displayed in-place on terminal (ANSI codes); NOT sent to orchestrator.
- Pitfall 1: sounddevice callback runs on non-asyncio thread — use loop.call_soon_threadsafe.
- Pitfall 2: interim_results=True is REQUIRED alongside utterance_end_ms for UtteranceEnd to fire.

NOTE: Deepgram SDK 6.x (current GA as of 2026) uses a new Fern-generated API that differs from
older research patterns. Key changes from SDK <4.x:
  - Connection: async with client.listen.v1.connect(model=...) as socket
  - Events: EventType.MESSAGE for all messages (typed union via isinstance)
  - Types: ListenV1Results (transcripts), ListenV1UtteranceEnd, ListenV1SpeechStarted
  - Send audio: await socket.send_media(bytes)
  - Start listener task: asyncio.create_task(socket.start_listening())
"""

import asyncio
import logging
import sys
from collections.abc import Callable

import sounddevice as sd
from deepgram import AsyncDeepgramClient
from deepgram.core.events import EventType
from deepgram.listen.v1.types import (
    ListenV1Results,
    ListenV1SpeechStarted,
    ListenV1UtteranceEnd,
)

logger = logging.getLogger(__name__)

# Audio capture constants (linear16 PCM for Deepgram nova-3)
_SAMPLE_RATE = 16000
_CHANNELS = 1
_DTYPE = "int16"
_BLOCKSIZE = 1024  # ~64ms at 16kHz — low latency without excessive callback overhead


class STTPipeline:
    """Deepgram Nova-3 WebSocket STT with sounddevice mic capture and UtteranceEnd turn detection.

    Per D-09: Deepgram Nova-3 via WebSocket SDK with interim results.
    Per D-05: Deepgram built-in VAD only (no Silero).
    Per D-06: UtteranceEnd fires -> accumulated transcript sent to orchestrator.
    Per D-10: Interim transcripts displayed in-place on terminal.

    Usage::

        pipeline = STTPipeline(api_key=settings.deepgram_api_key)
        stop = asyncio.Event()
        asyncio.create_task(pipeline.start_listening(stop))
        utterance = await pipeline.utterance_queue.get()

    Thread safety: _handle_message is only called from the asyncio event loop via
    start_listening()'s MessageEvent callback.
    """

    def __init__(
        self,
        api_key: str,
        on_speech_started: Callable[[], None] | None = None,
    ) -> None:
        """Initialise the pipeline.

        Args:
            api_key: Deepgram API key. Never logged (T-05-04).
            on_speech_started: Optional callback invoked when Deepgram fires
                SpeechStarted (VAD detected utterance beginning). Used by Plan 03
                barge-in to cancel the TTS task.
        """
        self._api_key = api_key
        self._on_speech_started = on_speech_started
        self._transcript_parts: list[str] = []
        self.utterance_queue: asyncio.Queue[str] = asyncio.Queue()

    # ------------------------------------------------------------------
    # Core message handler — called from asyncio loop via start_listening
    # ------------------------------------------------------------------

    def _handle_message(self, message: object) -> None:
        """Dispatch a Deepgram WebSocket message to the appropriate handler.

        Called from the EventType.MESSAGE callback registered in start_listening().
        Each message is a typed union: ListenV1Results | ListenV1UtteranceEnd |
        ListenV1SpeechStarted | ListenV1Metadata.
        """
        if isinstance(message, ListenV1Results):
            self._on_transcript(message)
        elif isinstance(message, ListenV1UtteranceEnd):
            self._on_utterance_end(message)
        elif isinstance(message, ListenV1SpeechStarted):
            self._on_speech_started_event(message)
        # ListenV1Metadata and unknown types are ignored

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_transcript(self, result: ListenV1Results) -> None:
        """Handle a transcript message.

        If interim (is_final=False): display in-place on terminal but do NOT accumulate.
        If final (is_final=True): accumulate in _transcript_parts for UtteranceEnd join.
        """
        # Guard: some results may have no alternatives (e.g. VAD silence frames)
        try:
            text = result.channel.alternatives[0].transcript
        except (AttributeError, IndexError):
            return

        if not text:
            return

        if result.is_final:
            self._transcript_parts.append(text)
        else:
            # D-10: display interim in-place on terminal (not sent to orchestrator)
            self._display_interim(text)

    def _on_utterance_end(self, _event: ListenV1UtteranceEnd) -> None:
        """Handle UtteranceEnd — join accumulated finals and push to utterance_queue.

        D-06: Only push if accumulated text is non-empty (ignore silence-only utterances).
        """
        joined = " ".join(self._transcript_parts).strip()
        self._transcript_parts = []

        if not joined:
            return

        self._finalize_transcript_line(joined)
        self.utterance_queue.put_nowait(joined)

    def _on_speech_started_event(self, _event: ListenV1SpeechStarted) -> None:
        """Handle SpeechStarted — invoke barge-in callback if registered."""
        if self._on_speech_started is not None:
            self._on_speech_started()

    # ------------------------------------------------------------------
    # Terminal display helpers (D-10)
    # ------------------------------------------------------------------

    @staticmethod
    def _display_interim(text: str) -> None:
        """Overwrite current terminal line with interim transcript in-place."""
        sys.stdout.write(f"\r\033[K{text}")
        sys.stdout.flush()

    @staticmethod
    def _finalize_transcript_line(text: str) -> None:
        """Clear current line and print final transcript with 'You:' prefix."""
        sys.stdout.write(f"\r\033[KYou: {text}\n")
        sys.stdout.flush()

    # ------------------------------------------------------------------
    # Main async entry point
    # ------------------------------------------------------------------

    async def start_listening(self, stop_event: asyncio.Event) -> None:
        """Start mic capture and Deepgram WebSocket streaming.

        Opens a sounddevice InputStream and streams PCM audio to Deepgram Nova-3
        via WebSocket. Runs until stop_event is set.

        The sounddevice callback runs on a non-asyncio thread. Audio bytes are
        bridged to the asyncio loop via loop.call_soon_threadsafe (Pitfall 1).

        Args:
            stop_event: Set to stop listening and close the WebSocket connection.
        """
        client = AsyncDeepgramClient(api_key=self._api_key)
        audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
        loop = asyncio.get_event_loop()

        def _sd_callback(
            indata: "sd.np.ndarray",
            frames: int,
            time_info: object,
            status: "sd.CallbackFlags",
        ) -> None:
            """sounddevice callback — runs on PortAudio thread (not asyncio).

            Pitfall 1: must use call_soon_threadsafe to bridge to asyncio queue.
            """
            if status:
                logger.warning("sounddevice status: %s", status)
            loop.call_soon_threadsafe(audio_queue.put_nowait, indata.tobytes())

        async with client.listen.v1.connect(
            model="nova-3",
            language="en-US",
            encoding="linear16",
            sample_rate=_SAMPLE_RATE,
            channels=_CHANNELS,
            interim_results=True,        # Pitfall 2: REQUIRED for UtteranceEnd to fire
            utterance_end_ms="1000",     # 1 second of silence triggers UtteranceEnd
            vad_events=True,             # Enables SpeechStarted for barge-in (D-03)
            endpointing=300,             # 300ms silence finalizes a word
        ) as socket:
            # Register message handler on the socket's event emitter
            socket.on(EventType.MESSAGE, self._handle_message)
            socket.on(EventType.ERROR, lambda err: logger.warning("Deepgram error: %s", err))

            # Start background listener task (emits EventType.MESSAGE for each frame)
            listen_task = asyncio.create_task(socket.start_listening())

            # Open mic input stream (sounddevice) and stream audio to Deepgram
            stream = sd.InputStream(
                samplerate=_SAMPLE_RATE,
                channels=_CHANNELS,
                dtype=_DTYPE,
                blocksize=_BLOCKSIZE,
                callback=_sd_callback,
            )
            with stream:
                while not stop_event.is_set():
                    try:
                        chunk = await asyncio.wait_for(audio_queue.get(), timeout=0.1)
                        await socket.send_media(chunk)
                    except asyncio.TimeoutError:
                        # No audio in queue — check stop_event and loop
                        continue

            # Stop Deepgram connection gracefully
            await socket.send_close_stream()
            listen_task.cancel()
            try:
                await listen_task
            except asyncio.CancelledError:
                pass
