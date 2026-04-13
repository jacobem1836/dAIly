"""Voice I/O package for dAIly.

Provides TTS (Cartesia Sonic-3), STT (Deepgram Nova-3), barge-in coordination,
and the top-level voice session loop.

Public API (populated as modules are built across Phase 5 plans):
    - TTSPipeline: Cartesia WebSocket TTS with sentence streaming
    - split_sentences: Sentence splitter utility for TTS input
    - STTPipeline: Deepgram Nova-3 WebSocket STT with mic capture and UtteranceEnd turn detection
"""
from daily.voice.tts import TTSPipeline, split_sentences
from daily.voice.stt import STTPipeline

__all__ = ["TTSPipeline", "split_sentences", "STTPipeline"]
