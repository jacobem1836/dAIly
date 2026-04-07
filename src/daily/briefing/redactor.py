"""
Redactor: per-item LLM summarisation and credential stripping.

Security boundary: ensures no raw email/message bodies reach the narrator LLM.

D-09: Credential regex strips sensitive values before content crosses to narrator.
D-10: Redaction runs per-item (not per-briefing) via GPT-4.1 mini.
T-02-07: Bounded capture `{1,200}` prevents catastrophic backtracking.
T-02-15: Semaphore caps concurrent OpenAI calls to prevent rate limiting.
"""

import asyncio
import re

from openai import AsyncOpenAI

from daily.briefing.models import RankedEmail
from daily.integrations.models import MessageMetadata

# ---------------------------------------------------------------------------
# Credential pattern (D-09 / T-02-07)
# ---------------------------------------------------------------------------
# Value capture uses [^\s,;"\'>]{1,200} — stops at comma, semicolon, quotes,
# angle brackets (JSON/HTML delimiters). Bounded {1,200} prevents catastrophic
# backtracking on large inputs.
CREDENTIAL_PATTERN = re.compile(
    r"(?:"
    # Key-value patterns: password: xxx, token=xxx, etc.
    # The keyword itself may appear inside JSON quotes (e.g. "password"), so
    # allow an optional closing quote after the keyword before the separator.
    # Value capture handles two contexts:
    #   - Quoted (JSON): match `"value"` including surrounding quotes
    #   - Unquoted (plain text/HTML): stop at comma, semicolon, angle bracket, whitespace
    # Bounded {1,200} prevents catastrophic backtracking (T-02-07).
    r"(?:password|passwd|token|api_key|apikey|secret|auth|authorization|bearer)"
    r'"?'                                       # optional closing quote (JSON key)
    r"\s*[:=]\s*"
    r'(?:"[^"]{1,200}"'                        # quoted value (JSON): include surrounding quotes
    r'|[^\s,;"\'><]{1,200})'                   # unquoted value (plain/HTML)
    r"|"
    # URL auth params: ?token=xxx&, ?key=xxx
    r'https?://[^\s<>"]{0,500}[?&](?:token|key|secret|auth|session_id)=[^\s<>"&]{1,200}'
    r")",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Rate-limit guard (T-02-15)
# ---------------------------------------------------------------------------
# Caps concurrent OpenAI calls at 3 to avoid hitting rate limits when
# processing large email/Slack batches.
_LLM_SEMAPHORE = asyncio.Semaphore(3)

# ---------------------------------------------------------------------------
# Summarise system prompt
# ---------------------------------------------------------------------------
_SUMMARISE_SYSTEM_PROMPT = (
    "Extract only the key actionable facts from this message. Be concise. "
    "Omit pleasantries, signatures, disclaimers, and boilerplate. "
    "Output plain text, not JSON."
)


def strip_credentials(text: str) -> str:
    """Replace all credential patterns in text with [REDACTED].

    Handles plain text, JSON, and HTML contexts without mangling surrounding
    delimiters. Uses bounded capture to prevent catastrophic backtracking.
    """
    return CREDENTIAL_PATTERN.sub("[REDACTED]", text)


async def summarise_and_redact(raw_body: str, client: AsyncOpenAI) -> str:
    """Summarise a raw message body via GPT-4.1 mini and strip credential patterns.

    Returns an empty string for empty/whitespace-only bodies (no LLM call).
    Acquires the shared semaphore before calling OpenAI to prevent rate limiting.
    """
    if not raw_body.strip():
        return ""

    async with _LLM_SEMAPHORE:
        response = await client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": _SUMMARISE_SYSTEM_PROMPT},
                {"role": "user", "content": raw_body},
            ],
            max_tokens=200,
        )

    summary = response.choices[0].message.content
    return strip_credentials(summary)


async def redact_emails(
    emails: list[RankedEmail],
    raw_bodies: dict[str, str],
    client: AsyncOpenAI,
) -> list[RankedEmail]:
    """Summarise and redact all emails concurrently.

    For each email, looks up its raw body by message_id, calls
    summarise_and_redact, and sets email.summary. Runs all calls
    concurrently via asyncio.gather — semaphore inside summarise_and_redact
    provides rate-limit protection.

    Returns the same list with summary fields populated.
    """

    async def _process(email: RankedEmail) -> RankedEmail:
        body = raw_bodies.get(email.metadata.message_id, "")
        email.summary = await summarise_and_redact(body, client)
        return email

    updated = await asyncio.gather(*[_process(e) for e in emails])
    return list(updated)


async def redact_messages(
    messages: list[MessageMetadata],
    raw_texts: dict[str, str],
    client: AsyncOpenAI,
) -> dict[str, str]:
    """Summarise and redact all Slack messages concurrently.

    Returns a dict mapping message_id -> redacted summary. Runs all calls
    concurrently via asyncio.gather.
    """

    async def _process(message: MessageMetadata) -> tuple[str, str]:
        text = raw_texts.get(message.message_id, "")
        summary = await summarise_and_redact(text, client)
        return message.message_id, summary

    pairs = await asyncio.gather(*[_process(m) for m in messages])
    return dict(pairs)
