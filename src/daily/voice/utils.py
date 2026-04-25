"""Utility helpers for the voice loop."""

from __future__ import annotations

_BACKCHANNEL_PHRASES: frozenset[str] = frozenset({
    "yeah", "yep", "yup", "yes", "ok", "okay", "right", "got it",
    "uh-huh", "mm-hmm", "mmhm", "sure", "alright", "cool", "go on",
    "continue", "and", "so", "mm", "hmm", "interesting", "i see",
    "ah", "oh",
})


def _is_backchannel(text: str) -> bool:
    """Return True when `text` looks like a passive listening token.

    Match criteria (per Phase 17 CONTEXT.md):
      - <= 3 words
      - normalized (strip + lower + strip trailing .,!?) is in _BACKCHANNEL_PHRASES
    """
    if not text:
        return False
    normalized = text.strip().lower().rstrip(".,!?")
    if not normalized:
        return False
    if len(normalized.split()) > 3:
        return False
    return normalized in _BACKCHANNEL_PHRASES
