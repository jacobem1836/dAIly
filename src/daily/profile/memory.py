"""Phase 9 cross-session memory module (INTEL-02).

Responsibilities:
  - extract_and_store_memories: LLM-driven fact extraction at session end,
    with cosine-distance dedup and memory_enabled gating (D-03, D-04, D-05).
  - retrieve_relevant_memories: implemented in Plan 03 (this file is extended).

Design constraints (CONTEXT.md):
  - D-01: Custom extraction, not mem0/langmem. text-embedding-3-small (1536d).
  - D-04: Cosine dedup at insert; threshold 0.1.
  - D-05: memory_enabled=False is a hard gate — no LLM calls, no DB writes.
  - Specifics #2: extract_and_store_memories must NEVER raise.

Security (PLAN.md threat model):
  - T-09-05: LLM JSON validated strictly; non-string facts stripped; capped at 10.
  - T-09-06: _MAX_FACTS_PER_SESSION=10 hard cap + max_tokens=600 on LLM call.
  - T-09-07: Log messages include exception class/msg only — never raw transcript.
"""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from openai import AsyncOpenAI
from sqlalchemy import select

from daily.config import Settings
from daily.db.models import MemoryFact
from daily.profile.service import load_profile

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Extraction prompt (per CONTEXT.md D-01 and RESEARCH.md §"Extraction Prompt")
# ---------------------------------------------------------------------------

EXTRACTION_SYSTEM_PROMPT = (
    "You are a personal assistant reading a conversation transcript. "
    "Extract durable personal facts that would help a briefing assistant "
    "in future sessions. Examples: travel plans, preferences, recurring "
    "commitments, personal context.\n\n"
    "Rules:\n"
    "- Extract at most 10 facts.\n"
    "- Each fact must be a single, self-contained statement.\n"
    "- Only extract facts stated by the user, not the assistant.\n"
    "- Do not extract ephemeral facts (e.g., 'user asked about today\u2019s weather').\n"
    "- Do not extract facts already obvious from the briefing context.\n\n"
    'Output MUST be valid JSON: {"facts": ["fact one", "fact two", ...]}\n'
    'If no durable facts exist, output: {"facts": []}'
)

_MAX_FACTS_PER_SESSION = 10
_DEDUP_DISTANCE_THRESHOLD = 0.1


# ---------------------------------------------------------------------------
# OpenAI client seam (tests monkeypatch this function)
# ---------------------------------------------------------------------------


def _get_openai_client() -> AsyncOpenAI:
    """Return an AsyncOpenAI client. Tests monkeypatch this function."""
    return AsyncOpenAI(api_key=Settings().openai_api_key)


# ---------------------------------------------------------------------------
# Embedding helper
# ---------------------------------------------------------------------------


async def _embed(text: str, client: AsyncOpenAI) -> list[float]:
    """Generate a 1536-dim embedding for ``text`` via text-embedding-3-small."""
    response = await client.embeddings.create(
        model="text-embedding-3-small",
        input=text,
    )
    return response.data[0].embedding


# ---------------------------------------------------------------------------
# Dedup + insert
# ---------------------------------------------------------------------------


async def _store_fact(
    user_id: int,
    fact_text: str,
    embedding: list[float],
    session_id: str,
    session: AsyncSession,
) -> None:
    """Insert fact iff no near-duplicate exists (cosine distance < 0.1).

    Uses pgvector's cosine_distance operator via the ORM (RESEARCH.md Pattern 4).
    A distance of 0.0 means identical vectors; threshold 0.1 catches paraphrases.
    """
    dup_stmt = (
        select(MemoryFact.id)
        .where(MemoryFact.user_id == user_id)
        .where(
            MemoryFact.embedding.cosine_distance(embedding)
            < _DEDUP_DISTANCE_THRESHOLD
        )
        .limit(1)
    )
    existing = (await session.execute(dup_stmt)).scalar()
    if existing is not None:
        logger.debug(
            "memory dedup skip: user=%d fact=%r dup=%s",
            user_id,
            fact_text[:80],
            existing,
        )
        return
    session.add(
        MemoryFact(
            user_id=user_id,
            fact_text=fact_text,
            embedding=embedding,
            source_session_id=session_id,
        )
    )
    await session.commit()


# ---------------------------------------------------------------------------
# Public extraction entry point
# ---------------------------------------------------------------------------


async def extract_and_store_memories(
    user_id: int,
    session_history: list[dict],
    session_id: str,
    db_session: AsyncSession,
) -> None:
    """Extract durable facts from a voice session transcript and persist them.

    Fire-and-forget entry point called from Plan 04's voice session finally block
    via ``asyncio.create_task``. Must NEVER raise (CONTEXT.md specifics #2).
    All errors are caught and logged.

    Gating order (belt-and-braces, D-05):
      1. memory_enabled=False          -> return immediately (no LLM calls)
      2. Empty session_history          -> return (nothing to extract)
      3. No user turns in history       -> return
      4. LLM / network / parse failure -> logged + return

    Args:
        user_id: Authenticated user identifier.
        session_history: List of ``{"role": ..., "content": ...}`` dicts from
            the voice session (produced by Plan 04's voice loop).
        session_id: Opaque string identifying the current session.
        db_session: AsyncSession provided by the caller; committed per-fact.
    """
    try:
        if not session_history:
            return

        user_turns = [
            m
            for m in session_history
            if isinstance(m, dict) and m.get("role") == "user"
        ]
        if not user_turns:
            return

        preferences = await load_profile(user_id, db_session)
        if not preferences.memory_enabled:
            logger.debug(
                "memory extraction skipped: user=%d memory_enabled=False",
                user_id,
            )
            return

        client = _get_openai_client()

        transcript = "\n".join(
            f"{m.get('role', 'unknown')}: {m.get('content', '')}"
            for m in session_history
        )

        try:
            response = await client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": transcript},
                ],
                response_format={"type": "json_object"},
                max_tokens=600,
            )
            raw = response.choices[0].message.content or ""
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning(
                "extract_and_store_memories: LLM JSON parse failed: %s", exc
            )
            return
        except (KeyError, ValueError) as exc:
            logger.warning(
                "extract_and_store_memories: LLM response malformed: %s", exc
            )
            return

        facts = parsed.get("facts")
        if not isinstance(facts, list):
            logger.warning(
                "extract_and_store_memories: 'facts' key missing or not a list"
            )
            return

        # T-09-05: filter non-string items; T-09-06: cap at _MAX_FACTS_PER_SESSION
        facts = [
            f.strip()
            for f in facts
            if isinstance(f, str) and f.strip()
        ][:_MAX_FACTS_PER_SESSION]

        for fact in facts:
            embedding = await _embed(fact, client)
            await _store_fact(
                user_id=user_id,
                fact_text=fact,
                embedding=embedding,
                session_id=session_id,
                session=db_session,
            )

    except Exception as exc:
        logger.warning(
            "extract_and_store_memories: unexpected failure: %s", exc
        )
