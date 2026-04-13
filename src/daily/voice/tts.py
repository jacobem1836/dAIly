"""TTS pipeline: Cartesia Sonic-3 WebSocket streaming with sounddevice PCM playback.

Implements sentence-by-sentence streaming (D-07) to begin playback before the full
LLM response is generated. Checks stop_event between every audio chunk (D-04) to
support barge-in without waiting for sentence completion.
"""
import asyncio
import re

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
                        if stop_event.is_set():
                            break  # Barge-in detected — stop immediately (D-04)
                        if response.type == "chunk" and response.audio:
                            output_stream.write(response.audio)
                finally:
                    output_stream.stop()
                    output_stream.close()
