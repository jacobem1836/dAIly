"""TTS pipeline: Cartesia Sonic-3 WebSocket streaming with sounddevice PCM playback.

Implements sentence-by-sentence streaming (D-07) to begin playback before the full
LLM response is generated. Checks stop_event between every audio chunk (D-04) to
support barge-in without waiting for sentence completion.

Plan 17-04: play_streaming_tokens() streams LLM token deltas to Cartesia by
accumulating tokens and pushing each completed sentence (`. `, `! `, `? `, `\n`)
without waiting for the full LLM response — delivering the first spoken word
noticeably sooner than the non-streaming path.
"""
import asyncio
import re
from collections.abc import AsyncIterator

import sounddevice as sd
from cartesia import AsyncCartesia

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

CARTESIA_SAMPLE_RATE = 44100
CARTESIA_OUTPUT_FORMAT = {
    "container": "raw",
    "encoding": "pcm_f32le",
    "sample_rate": CARTESIA_SAMPLE_RATE,
}
DEFAULT_VOICE_ID = "6ccbfb76-1fc6-48f7-b71d-91ac6298247b"

# Minimum character length for a sentence segment before it gets merged into the
# next segment (Pitfall 7: very short Cartesia pushes add per-segment latency).
# Segments under this threshold are concatenated with the following segment.
MIN_CHARS = 6

# Common abbreviations that end with a period — we must NOT split on these.
_ABBREV_PATTERN = re.compile(
    r"\b(?:Mr|Mrs|Ms|Dr|Prof|Sr|Jr|vs|etc|No|Vol|Dept|Fig|approx|est|Corp|Inc|Ltd)\."
)

# Sentence boundary pattern: sentence-ending punctuation followed by whitespace.
_BOUNDARY_PATTERN = re.compile(r"(?<=[.!?])\s+")

# Token-stream sentence boundaries for play_streaming_tokens.
# Two-character markers: ". ", "! ", "? ", and newline (treated as boundary too).
_SENTENCE_BOUNDARIES: tuple[str, ...] = (". ", "! ", "? ", "\n")


def _split_at_boundary(buffer: str) -> tuple[str | None, str]:
    """Return (sentence, remainder). sentence is None if no boundary found.

    Finds the EARLIEST boundary occurrence in buffer and splits there.

    Args:
        buffer: Accumulated token text to scan for a sentence boundary.

    Returns:
        Tuple of (sentence_including_boundary, remaining_buffer) when a boundary
        is found, or (None, buffer) when no boundary exists yet.
    """
    best_idx = -1
    best_len = 0
    for marker in _SENTENCE_BOUNDARIES:
        idx = buffer.find(marker)
        if idx != -1 and (best_idx == -1 or idx < best_idx):
            best_idx = idx
            best_len = len(marker)
    if best_idx == -1:
        return None, buffer
    end = best_idx + best_len
    return buffer[:end], buffer[end:]


# --------------------------------------------------------------------------- #
# Public utility
# --------------------------------------------------------------------------- #


def split_sentences(text: str) -> list[str]:
    """Split *text* into sentence segments suitable for Cartesia per-sentence pushing.

    Rules:
    - Split at sentence-ending punctuation ([.!?]) followed by whitespace.
    - Do NOT split on common abbreviations (Mr., Dr., etc.).
    - Merge any segment shorter than MIN_CHARS into the following segment to
      avoid Cartesia per-segment latency stuttering.
    - Always return a non-empty list; empty or single-segment input returns
      ``[text]``.

    Args:
        text: The raw text to split.

    Returns:
        A list of one or more sentence segments.
    """
    if not text:
        return [text]

    # Replace abbreviation periods with a placeholder to protect them from splitting.
    placeholder = "\x00ABBREV\x00"
    protected = _ABBREV_PATTERN.sub(lambda m: m.group(0)[:-1] + placeholder, text)

    # Split on sentence boundaries.
    raw_segments = _BOUNDARY_PATTERN.split(protected)

    # Restore abbreviation periods.
    segments = [seg.replace(placeholder, ".") for seg in raw_segments if seg]

    if not segments:
        return [text]

    # Merge short segments: accumulate segments until buffer reaches MIN_CHARS,
    # then flush. This prevents very short Cartesia pushes (Pitfall 7) while
    # preserving natural sentence boundaries where possible.
    merged: list[str] = []
    buffer = ""
    for segment in segments:
        if buffer:
            candidate = buffer + " " + segment
        else:
            candidate = segment

        if len(candidate) < MIN_CHARS:
            # Accumulate — not long enough to flush yet
            buffer = candidate
        else:
            # Long enough — flush this combined segment
            merged.append(candidate)
            buffer = ""

    if buffer:
        # Remaining short buffer: attach to the last merged segment if any,
        # otherwise emit as its own segment.
        if merged:
            merged[-1] = merged[-1] + " " + buffer
        else:
            merged.append(buffer)

    return merged if merged else [text]


# --------------------------------------------------------------------------- #
# TTSPipeline
# --------------------------------------------------------------------------- #


class TTSPipeline:
    """Streams TTS audio sentence-by-sentence via Cartesia Sonic-3 WebSocket.

    Usage::

        pipeline = TTSPipeline(api_key=settings.cartesia_api_key)
        stop = asyncio.Event()
        await pipeline.play_streaming("Hello. How can I help?", stop)
    """

    def __init__(self, api_key: str, voice_id: str = DEFAULT_VOICE_ID) -> None:
        self._api_key = api_key
        self._voice_id = voice_id

    async def play_streaming(self, text: str, stop_event: asyncio.Event) -> None:
        """Stream TTS audio sentence-by-sentence with barge-in support.

        Per D-07: Split text into sentences, push each to Cartesia WebSocket,
        begin playback as first chunk arrives.
        Per D-04: Check stop_event between EVERY audio chunk, not just sentences.
        Per D-08: Use sounddevice RawOutputStream for PCM playback.

        Pitfall 5: Use try/finally to ensure sounddevice stream closes on cancel.

        Args:
            text: The text to convert to speech.
            stop_event: When set, playback stops immediately (barge-in signal).
        """
        sentences = split_sentences(text)

        async with AsyncCartesia(api_key=self._api_key) as client:
            async with client.tts.websocket_connect() as connection:
                ctx = connection.context(
                    model_id="sonic-3",
                    voice={"mode": "id", "id": self._voice_id},
                    output_format=CARTESIA_OUTPUT_FORMAT,
                )

                for sentence in sentences:
                    await ctx.push(sentence)
                await ctx.no_more_inputs()

                output_stream = sd.RawOutputStream(
                    samplerate=CARTESIA_SAMPLE_RATE,
                    channels=1,
                    dtype="float32",
                )
                try:
                    output_stream.start()
                    async for response in ctx.receive():
                        if response.type == "chunk" and response.audio:
                            output_stream.write(response.audio)
                        if stop_event.is_set():
                            break  # Barge-in detected — finish current chunk, then stop (graceful fade-out)
                finally:
                    output_stream.stop()
                    output_stream.close()

    async def play_streaming_tokens(
        self,
        token_stream: AsyncIterator[str],
        stop_event: asyncio.Event,
    ) -> None:
        """Stream LLM token deltas to Cartesia, pushing one sentence at a time.

        Accumulates tokens into a buffer and flushes to Cartesia each time a
        sentence boundary ('. ', '! ', '? ', '\\n') is detected. Any remaining
        buffer at stream end is pushed as a final segment.

        Audio playback runs concurrently with token accumulation via
        asyncio.gather: a producer pushes sentences to Cartesia while a consumer
        reads audio chunks from ctx.receive() and writes them to sounddevice.

        Respects stop_event between tokens (producer) and between audio chunks
        (consumer), honouring Plan 01's graceful fade-out ordering — write the
        chunk first, then check stop_event.

        Args:
            token_stream: Async iterator of plain-text token delta strings.
            stop_event: When set, playback stops after the current audio chunk
                        (barge-in / graceful fade-out).
        """
        async with AsyncCartesia(api_key=self._api_key) as client:
            async with client.tts.websocket_connect() as connection:
                ctx = connection.context(
                    model_id="sonic-3",
                    voice={"mode": "id", "id": self._voice_id},
                    output_format=CARTESIA_OUTPUT_FORMAT,
                )

                output_stream = sd.RawOutputStream(
                    samplerate=CARTESIA_SAMPLE_RATE,
                    channels=1,
                    dtype="float32",
                )

                try:
                    output_stream.start()

                    async def _produce() -> None:
                        """Consume token_stream, push completed sentences to ctx."""
                        buffer = ""
                        async for delta in token_stream:
                            if stop_event.is_set():
                                break
                            buffer += delta
                            # Flush all completed sentences from the buffer.
                            while True:
                                sentence, remainder = _split_at_boundary(buffer)
                                if sentence is None:
                                    break
                                await ctx.push(sentence)
                                buffer = remainder
                        # Push any remaining text at stream end.
                        if buffer.strip():
                            await ctx.push(buffer)
                        await ctx.no_more_inputs()

                    async def _consume() -> None:
                        """Read Cartesia audio chunks and write to sounddevice."""
                        async for response in ctx.receive():
                            if response.type == "chunk" and response.audio:
                                output_stream.write(response.audio)
                            if stop_event.is_set():
                                break  # Graceful fade-out — write chunk first, then check

                    await asyncio.gather(_produce(), _consume())

                finally:
                    output_stream.stop()
                    output_stream.close()
