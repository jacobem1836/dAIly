"""Phase 9 memory module tests (INTEL-02).

Wave 0: memory_enabled flag defaults — runnable without DB.
Wave 1: extraction (Plan 02) — require async_db_session fixture.
Wave 1: retrieval/injection (Plan 03) — stubs pending Plan 03.
Wave 2: trigger wiring (Plan 04) — stub pending Plan 04.
"""
import pytest

from daily.profile.models import UserPreferences


# ---------------------------------------------------------------------------
# Wave 0: memory_enabled flag defaults (runnable now, no DB needed)
# ---------------------------------------------------------------------------


def test_memory_enabled_defaults_to_true():
    assert UserPreferences().memory_enabled is True


def test_memory_enabled_round_trips_false():
    prefs = UserPreferences.model_validate({"memory_enabled": False})
    assert prefs.memory_enabled is False


def test_memory_enabled_missing_key_defaults_to_true():
    prefs = UserPreferences.model_validate({})
    assert prefs.memory_enabled is True


# ---------------------------------------------------------------------------
# Wave 1 (Plan 02) — extraction tests
# ---------------------------------------------------------------------------


async def test_extract_facts_stores_embedding(async_db_session, monkeypatch):
    """extract_and_store_memories persists one MemoryFact row with correct fields."""
    from unittest.mock import AsyncMock, MagicMock

    from sqlalchemy import select

    from daily.db.models import MemoryFact
    from daily.profile import memory as memory_mod
    from daily.profile.service import _ensure_default_user

    # Mock OpenAI client — chat returns a JSON fact, embeddings return a vector
    mock_client = MagicMock()
    mock_chat = AsyncMock(
        return_value=MagicMock(
            choices=[
                MagicMock(
                    message=MagicMock(
                        content='{"facts": ["User travels to Sydney next week"]}'
                    )
                )
            ]
        )
    )
    mock_client.chat.completions.create = mock_chat

    mock_embed = AsyncMock(
        return_value=MagicMock(data=[MagicMock(embedding=[0.1] * 1536)])
    )
    mock_client.embeddings.create = mock_embed

    monkeypatch.setattr(memory_mod, "_get_openai_client", lambda: mock_client)

    # Ensure the user row exists (PoC single-user workaround)
    await _ensure_default_user(1, async_db_session)
    await async_db_session.commit()

    await memory_mod.extract_and_store_memories(
        user_id=1,
        session_history=[{"role": "user", "content": "Going to Sydney next week"}],
        session_id="sess-1",
        db_session=async_db_session,
    )

    rows = (
        await async_db_session.execute(
            select(MemoryFact).where(MemoryFact.user_id == 1)
        )
    ).scalars().all()

    assert len(rows) == 1
    assert rows[0].fact_text == "User travels to Sydney next week"
    assert rows[0].source_session_id == "sess-1"
    assert len(rows[0].embedding) == 1536


async def test_extraction_skipped_when_disabled(async_db_session, monkeypatch):
    """When memory_enabled=False no LLM calls are made and no rows are written."""
    from unittest.mock import AsyncMock, MagicMock

    from sqlalchemy import select

    from daily.db.models import MemoryFact
    from daily.profile import memory as memory_mod
    from daily.profile.service import _ensure_default_user, upsert_preference

    # Mock OpenAI — should NEVER be called
    mock_client = MagicMock()
    mock_chat = AsyncMock()
    mock_client.chat.completions.create = mock_chat
    mock_embed = AsyncMock()
    mock_client.embeddings.create = mock_embed
    monkeypatch.setattr(memory_mod, "_get_openai_client", lambda: mock_client)

    # Persist user row and set memory_enabled=False
    await _ensure_default_user(2, async_db_session)
    await async_db_session.commit()
    await upsert_preference(2, "memory_enabled", "false", async_db_session)

    await memory_mod.extract_and_store_memories(
        user_id=2,
        session_history=[{"role": "user", "content": "I love coffee"}],
        session_id="sess-2",
        db_session=async_db_session,
    )

    rows = (
        await async_db_session.execute(
            select(MemoryFact).where(MemoryFact.user_id == 2)
        )
    ).scalars().all()
    assert len(rows) == 0
    assert mock_chat.call_count == 0
    assert mock_embed.call_count == 0


async def test_dedup_prevents_duplicate_insert(async_db_session, monkeypatch):
    """A fact whose embedding is within cosine distance 0.1 is NOT re-inserted."""
    from unittest.mock import AsyncMock, MagicMock

    from sqlalchemy import select

    from daily.db.models import MemoryFact
    from daily.profile import memory as memory_mod
    from daily.profile.service import _ensure_default_user

    KNOWN_EMBEDDING = [0.5] * 1536

    # Seed an existing MemoryFact with the known embedding
    await _ensure_default_user(3, async_db_session)
    await async_db_session.commit()
    existing = MemoryFact(
        user_id=3,
        fact_text="User already knows Sydney",
        embedding=KNOWN_EMBEDDING,
        source_session_id="seed-session",
    )
    async_db_session.add(existing)
    await async_db_session.commit()

    # Mock LLM to return the same near-duplicate fact + identical embedding
    mock_client = MagicMock()
    mock_chat = AsyncMock(
        return_value=MagicMock(
            choices=[
                MagicMock(
                    message=MagicMock(
                        content='{"facts": ["User already knows Sydney"]}'
                    )
                )
            ]
        )
    )
    mock_client.chat.completions.create = mock_chat
    # Embedding within 0.05 — same vector = cosine distance 0
    mock_embed = AsyncMock(
        return_value=MagicMock(data=[MagicMock(embedding=KNOWN_EMBEDDING)])
    )
    mock_client.embeddings.create = mock_embed
    monkeypatch.setattr(memory_mod, "_get_openai_client", lambda: mock_client)

    await memory_mod.extract_and_store_memories(
        user_id=3,
        session_history=[{"role": "user", "content": "Going to Sydney again"}],
        session_id="sess-3",
        db_session=async_db_session,
    )

    rows = (
        await async_db_session.execute(
            select(MemoryFact).where(MemoryFact.user_id == 3)
        )
    ).scalars().all()
    # Still only 1 row — the duplicate was deduplicated
    assert len(rows) == 1


async def test_extraction_swallows_errors(monkeypatch):
    """extract_and_store_memories never raises even on LLM or parse errors."""
    from unittest.mock import AsyncMock, MagicMock

    from daily.profile import memory as memory_mod

    # Test 1: network/runtime error from chat.completions.create
    mock_client_1 = MagicMock()
    mock_client_1.chat.completions.create = AsyncMock(
        side_effect=RuntimeError("network error")
    )
    monkeypatch.setattr(memory_mod, "_get_openai_client", lambda: mock_client_1)

    # Must not raise — swallowed and logged
    mock_session = MagicMock()
    mock_session.execute = AsyncMock()

    # We need to mock load_profile to return memory_enabled=True
    from daily.profile.models import UserPreferences

    async def mock_load_profile(user_id, session):
        return UserPreferences(memory_enabled=True)

    monkeypatch.setattr(memory_mod, "load_profile", mock_load_profile)

    try:
        await memory_mod.extract_and_store_memories(
            user_id=1,
            session_history=[{"role": "user", "content": "Test"}],
            session_id="sess-err",
            db_session=mock_session,
        )
    except Exception as exc:
        pytest.fail(f"extract_and_store_memories raised unexpectedly: {exc}")

    # Test 2: JSON parse failure (LLM returns non-JSON string)
    mock_client_2 = MagicMock()
    mock_client_2.chat.completions.create = AsyncMock(
        return_value=MagicMock(
            choices=[MagicMock(message=MagicMock(content="not valid json at all"))]
        )
    )
    monkeypatch.setattr(memory_mod, "_get_openai_client", lambda: mock_client_2)

    try:
        await memory_mod.extract_and_store_memories(
            user_id=1,
            session_history=[{"role": "user", "content": "Test"}],
            session_id="sess-parse-err",
            db_session=mock_session,
        )
    except Exception as exc:
        pytest.fail(f"extract_and_store_memories raised on parse error: {exc}")


# ---------------------------------------------------------------------------
# Wave 1 (Plan 03) — retrieval + injection stubs
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="pending Plan 03 implementation")
async def test_retrieve_relevant_facts():
    raise NotImplementedError


@pytest.mark.skip(reason="pending Plan 03 implementation")
async def test_retrieval_skipped_when_disabled():
    raise NotImplementedError


@pytest.mark.skip(reason="pending Plan 03 implementation")
async def test_session_state_includes_memories():
    raise NotImplementedError


# ---------------------------------------------------------------------------
# Wave 2 (Plan 04) — trigger wiring
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="pending Plan 04 implementation")
async def test_no_hallucination_loop():
    raise NotImplementedError
