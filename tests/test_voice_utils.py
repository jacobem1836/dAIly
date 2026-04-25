"""Unit tests for daily.voice.utils — _is_backchannel helper."""
from daily.voice.utils import _is_backchannel


def test_yeah_is_backchannel() -> None:
    assert _is_backchannel("yeah") is True


def test_yeah_case_insensitive() -> None:
    assert _is_backchannel("Yeah.") is True


def test_uh_huh_is_backchannel() -> None:
    assert _is_backchannel("uh-huh") is True


def test_got_it_is_backchannel() -> None:
    assert _is_backchannel("got it") is True


def test_too_many_words_is_not_backchannel() -> None:
    assert _is_backchannel("yes please go ahead") is False


def test_not_in_phrase_set() -> None:
    assert _is_backchannel("schedule a meeting") is False


def test_empty_string_is_not_backchannel() -> None:
    assert _is_backchannel("") is False


def test_whitespace_only_is_not_backchannel() -> None:
    assert _is_backchannel("   ") is False
