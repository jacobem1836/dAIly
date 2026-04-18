"""Unit tests for structured logging infrastructure (OBS-01, OBS-02).

Tests cover:
- JSONFormatter output shape (ts, level, module, msg, ctx fields)
- JSONFormatter exc field on exception records
- ContextAdapter ctx injection (user_id, stage)
- configure_logging wires JSONFormatter onto root logger
- LOG_LEVEL=DEBUG makes debug records appear
- LOG_LEVEL=WARNING suppresses info records
- make_logger returns a LoggerAdapter
"""

import io
import json
import logging

import pytest

from daily.logging_config import (
    ContextAdapter,
    JSONFormatter,
    configure_logging,
    make_logger,
)


# ---------------------------------------------------------------------------
# Fixture: restore root logger state after each test to prevent pollution
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def restore_root_logger():
    """Capture root logger state and restore it after each test."""
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    original_level = root.level
    yield
    root.handlers = original_handlers
    root.setLevel(original_level)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_stream_handler() -> tuple[logging.StreamHandler, io.StringIO]:
    """Return a StreamHandler backed by a StringIO buffer with JSONFormatter attached."""
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(JSONFormatter())
    return handler, buf


def _capture_log(
    level: str = "INFO", logger_name: str = "test.module"
) -> tuple[logging.Logger, io.StringIO]:
    """Configure a named logger with a JSONFormatter StreamHandler and return both."""
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(JSONFormatter())
    logger = logging.getLogger(logger_name)
    logger.handlers = [handler]
    logger.setLevel(getattr(logging, level))
    logger.propagate = False
    return logger, buf


# ---------------------------------------------------------------------------
# OBS-01: JSONFormatter output shape
# ---------------------------------------------------------------------------


def test_json_formatter_emits_valid_json():
    """JSONFormatter.format() returns valid JSON with required fields."""
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="daily.briefing.pipeline",
        level=logging.INFO,
        pathname="pipeline.py",
        lineno=42,
        msg="Test message",
        args=(),
        exc_info=None,
    )
    output = formatter.format(record)
    parsed = json.loads(output)

    assert "ts" in parsed
    assert "level" in parsed
    assert "module" in parsed
    assert "msg" in parsed
    assert "ctx" in parsed
    assert parsed["level"] == "INFO"
    assert parsed["module"] == "daily.briefing.pipeline"
    assert parsed["msg"] == "Test message"
    assert parsed["ctx"] == {}


def test_json_formatter_includes_exception():
    """JSONFormatter includes 'exc' field when record has exc_info."""
    formatter = JSONFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        exc_info = sys.exc_info()

    record = logging.LogRecord(
        name="daily.test",
        level=logging.ERROR,
        pathname="test.py",
        lineno=1,
        msg="Error occurred",
        args=(),
        exc_info=exc_info,
    )
    output = formatter.format(record)
    parsed = json.loads(output)

    assert "exc" in parsed
    assert "ValueError" in parsed["exc"]
    assert "boom" in parsed["exc"]


# ---------------------------------------------------------------------------
# OBS-01: ContextAdapter ctx injection
# ---------------------------------------------------------------------------


def test_context_adapter_injects_ctx():
    """ContextAdapter injects user_id and stage into log record ctx field."""
    logger_name = "test.context_adapter"
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(JSONFormatter())

    base_logger = logging.getLogger(logger_name)
    base_logger.handlers = [handler]
    base_logger.setLevel(logging.DEBUG)
    base_logger.propagate = False

    adapter = ContextAdapter(
        base_logger,
        extra={"ctx": {"user_id": 1, "stage": "voice.loop"}},
    )
    adapter.info("Processing voice input")

    output = buf.getvalue().strip()
    parsed = json.loads(output)

    assert parsed["ctx"]["user_id"] == 1
    assert parsed["ctx"]["stage"] == "voice.loop"


# ---------------------------------------------------------------------------
# OBS-01 / OBS-02: configure_logging
# ---------------------------------------------------------------------------


def test_configure_logging_sets_json_handler():
    """configure_logging installs exactly one handler on root logger with JSONFormatter."""
    configure_logging("INFO")
    root = logging.getLogger()

    assert len(root.handlers) == 1
    assert isinstance(root.handlers[0].formatter, JSONFormatter)


# ---------------------------------------------------------------------------
# OBS-02: LOG_LEVEL verbosity control
# ---------------------------------------------------------------------------


def test_log_level_debug_shows_debug():
    """configure_logging('DEBUG') makes debug-level records appear in output."""
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(JSONFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.DEBUG)

    configure_logging("DEBUG")

    test_logger = logging.getLogger("test.debug_visible")
    test_logger.propagate = True
    test_logger.handlers = []
    test_logger.debug("debug record")

    output = buf.getvalue()
    # configure_logging replaces handlers, so re-capture from root's new handler
    # Use a fresh capture after configure_logging sets up its own handler
    new_buf = io.StringIO()
    root = logging.getLogger()
    root.handlers[0].stream = new_buf

    test_logger.debug("debug record visible")
    new_output = new_buf.getvalue()
    parsed = json.loads(new_output.strip())
    assert parsed["level"] == "DEBUG"
    assert "debug record visible" in parsed["msg"]


def test_log_level_warning_suppresses_info():
    """configure_logging('WARNING') suppresses info-level output."""
    configure_logging("WARNING")

    new_buf = io.StringIO()
    root = logging.getLogger()
    root.handlers[0].stream = new_buf

    test_logger = logging.getLogger("test.warning_suppresses")
    test_logger.propagate = True
    test_logger.handlers = []
    test_logger.info("this info should be suppressed")

    output = new_buf.getvalue()
    assert output == ""


# ---------------------------------------------------------------------------
# make_logger factory
# ---------------------------------------------------------------------------


def test_make_logger_returns_adapter():
    """make_logger returns a logging.LoggerAdapter instance."""
    adapter = make_logger("test.factory", user_id=42, stage="test.stage")
    assert isinstance(adapter, logging.LoggerAdapter)
