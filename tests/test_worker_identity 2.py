"""Unit tests for daily.worker.identity.parse_user_id_from_room."""
import pytest

from daily.worker.identity import parse_user_id_from_room


def test_standard_room_name_returns_user_id() -> None:
    assert parse_user_id_from_room("session-42-1714000000") == 42


def test_single_digit_user_id() -> None:
    assert parse_user_id_from_room("session-1-1") == 1


def test_non_session_room_returns_none() -> None:
    assert parse_user_id_from_room("not-a-session-room") is None


def test_non_integer_user_id_segment_returns_none() -> None:
    assert parse_user_id_from_room("session-abc-1234") is None


def test_empty_string_returns_none() -> None:
    assert parse_user_id_from_room("") is None


def test_empty_user_id_segment_returns_none() -> None:
    assert parse_user_id_from_room("session--1234") is None
