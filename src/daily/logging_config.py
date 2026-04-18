"""Structured logging infrastructure for dAIly.

Provides:
- JSONFormatter: formats log records as single-line JSON (D-02)
- ContextAdapter: injects user_id and stage into log ctx field (D-03)
- configure_logging: wires JSONFormatter onto root logger at startup (D-01, D-04)
- make_logger: factory for ContextAdapter instances

Usage in modules that want ctx injection:
    logger = make_logger(__name__, user_id=1, stage="precompute")
    logger.info("Starting pipeline")  # emits {"ctx": {"user_id": 1, "stage": "precompute"}, ...}

Existing modules using logging.getLogger(__name__) work unchanged — the formatter
intercepts at the handler level, so no call-site changes are required.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, MutableMapping


class JSONFormatter(logging.Formatter):
    """Format log records as single-line JSON per D-02.

    Output shape:
        {"ts": "<ISO-8601 UTC>", "level": "INFO", "module": "daily.briefing.pipeline",
         "msg": "...", "ctx": {...}}

    If the record carries exc_info, an "exc" field is appended.

    Security: json.dumps auto-escapes newlines and special characters — no raw string
    concatenation in log output (T-14-01 mitigated).
    """

    def format(self, record: logging.LogRecord) -> str:
        log_dict: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.name,  # use record.name (dotted path), not record.module (filename)
            "msg": record.getMessage(),
            "ctx": getattr(record, "ctx", {}),
        }
        if record.exc_info:
            log_dict["exc"] = self.formatException(record.exc_info)
        return json.dumps(log_dict)


class ContextAdapter(logging.LoggerAdapter):
    """Injects ctx dict into every log record via the process() hook.

    ctx carries user_id and stage per D-03 — no tokens, email bodies, or credentials
    (T-14-02 mitigated).

    Usage:
        adapter = ContextAdapter(logger, extra={"ctx": {"user_id": 1, "stage": "voice.loop"}})
        adapter.info("message")  # ctx injected automatically
    """

    def process(
        self, msg: str, kwargs: MutableMapping[str, Any]
    ) -> tuple[str, MutableMapping[str, Any]]:
        kwargs.setdefault("extra", {})["ctx"] = self.extra.get("ctx", {})
        return msg, kwargs


def configure_logging(log_level: str = "INFO") -> None:
    """Configure root logger with JSONFormatter. Call once at startup.

    Clears existing handlers before adding the JSON handler to prevent duplicate output
    (Pitfall 1: root.handlers.clear() required before addHandler).

    Args:
        log_level: One of DEBUG, INFO, WARNING, ERROR, CRITICAL. Defaults to INFO.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))


def make_logger(name: str, **ctx_fields: Any) -> logging.LoggerAdapter:
    """Return a ContextAdapter that injects ctx_fields into every log record.

    Args:
        name: Logger name, typically __name__ of the calling module.
        **ctx_fields: Context fields to inject (e.g., user_id=1, stage="precompute").

    Returns:
        ContextAdapter wrapping the named logger.
    """
    return ContextAdapter(logging.getLogger(name), extra={"ctx": ctx_fields})
