"""Tests for daily.voice package __init__ lazy-load mechanism.

Covers the __getattr__ dynamic import path in voice/__init__.py.
"""
import pytest


def test_voice_run_voice_session_accessible():
    """daily.voice.run_voice_session is importable via lazy __getattr__."""
    import daily.voice as voice

    func = voice.run_voice_session
    assert callable(func)


def test_voice_loop_module_accessible():
    """daily.voice.loop attribute lazily loads the loop submodule."""
    import daily.voice as voice

    loop_mod = voice.loop
    assert hasattr(loop_mod, "run_voice_session")


def test_voice_getattr_raises_for_unknown():
    """Accessing an unknown attribute raises AttributeError."""
    import daily.voice as voice

    with pytest.raises(AttributeError):
        _ = voice.nonexistent_attribute_xyz
