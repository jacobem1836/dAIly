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
from daily.voice.loop import run_voice_session

__all__ = ["TTSPipeline", "split_sentences", "STTPipeline", "VoiceTurnManager", "run_voice_session"]
