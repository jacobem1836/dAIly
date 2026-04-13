"""Voice I/O package for dAIly.

Provides TTS (Cartesia Sonic-3), STT (Deepgram Nova-3), barge-in coordination,
and the top-level voice session loop.

Public API (populated as modules are built across Phase 5 plans):
    - TTSPipeline: Cartesia WebSocket TTS with sentence streaming
    - split_sentences: Sentence splitter utility for TTS input
"""
from daily.voice.tts import TTSPipeline, split_sentences

__all__ = ["TTSPipeline", "split_sentences"]
