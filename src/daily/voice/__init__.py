"""Voice I/O package for dAIly.

Provides TTS (Cartesia Sonic-3), STT (Deepgram Nova-3), barge-in coordination,
and the top-level voice session loop.

Public API:
    - TTSPipeline: Cartesia WebSocket TTS with sentence streaming
    - split_sentences: Sentence splitter utility for TTS input
    - STTPipeline: Deepgram Nova-3 WebSocket STT with mic capture and UtteranceEnd turn detection
    - VoiceTurnManager: Barge-in coordination layer (TTS/STT concurrency with echo suppression)
    - run_voice_session: Top-level voice session mirroring _run_chat_session
"""
from daily.voice.tts import TTSPipeline, split_sentences
from daily.voice.stt import STTPipeline
from daily.voice.barge_in import VoiceTurnManager

# Lazy-load loop module to avoid pulling postgres deps at package import time.
# The submodule is still directly importable as `daily.voice.loop`.
import importlib as _importlib

def __getattr__(name: str):
    if name == "run_voice_session":
        _loop = _importlib.import_module("daily.voice.loop")
        return _loop.run_voice_session
    if name == "loop":
        return _importlib.import_module("daily.voice.loop")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["TTSPipeline", "split_sentences", "STTPipeline", "VoiceTurnManager", "run_voice_session"]
