"""Voice I/O package for dAIly.

Provides TTS (Cartesia Sonic-3), STT (Deepgram Nova-3), barge-in coordination,
and the top-level voice session loop.

Public API (populated as modules are built across Phase 5 plans):
    - STTPipeline: Deepgram Nova-3 WebSocket STT with mic capture and UtteranceEnd turn detection
"""
from daily.voice.stt import STTPipeline

__all__ = ["STTPipeline"]
