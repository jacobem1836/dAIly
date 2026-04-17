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


async def test_retrieve_relevant_facts(async_db_session, monkeypatch):
    """retrieve_relevant_memories returns top-K fact texts ordered by cosine similarity."""
    from unittest.mock import AsyncMock, MagicMock

    from sqlalchemy import select

    from daily.db.models import MemoryFact
    from daily.profile import memory as memory_mod
    from daily.profile.service import _ensure_default_user

    # Seed two MemoryFact rows with different embeddings
    await _ensure_default_user(10, async_db_session)
    await async_db_session.commit()

    # First fact: embedding [0.1, 0.0, ...] (1536 dims)
    embedding_a = [0.1] + [0.0] * 1535
    # Second fact: embedding [0.0, 0.1, ...] — different direction
    embedding_b = [0.0, 0.1] + [0.0] * 1534

    fact_a = MemoryFact(
        user_id=10,
        fact_text="User travels to Sydney",
        embedding=embedding_a,
        source_session_id="seed-a",
    )
    fact_b = MemoryFact(
        user_id=10,
        fact_text="User prefers concise emails",
        embedding=embedding_b,
        source_session_id="seed-b",
    )
    async_db_session.add(fact_a)
    async_db_session.add(fact_b)
    await async_db_session.commit()

    # Mock embeddings.create to return embedding_a (closest to fact_a)
    mock_client = MagicMock()
    mock_embed = AsyncMock(
        return_value=MagicMock(data=[MagicMock(embedding=embedding_a)])
    )
    mock_client.embeddings.create = mock_embed
    monkeypatch.setattr(memory_mod, "_get_openai_client", lambda: mock_client)

    results = await memory_mod.retrieve_relevant_memories(
        user_id=10,
        query_text="travel plans",
        db_session=async_db_session,
        top_k=2,
    )

    assert isinstance(results, list)
    assert len(results) == 2
    # fact_a should be closest (identical embedding)
    assert results[0] == "User travels to Sydney"


async def test_retrieval_skipped_when_disabled(async_db_session, monkeypatch):
    """retrieve_relevant_memories returns [] and never calls embeddings when memory_enabled=False."""
    from unittest.mock import AsyncMock, MagicMock

    from daily.db.models import MemoryFact
    from daily.profile import memory as memory_mod
    from daily.profile.service import _ensure_default_user, upsert_preference

    await _ensure_default_user(11, async_db_session)
    await async_db_session.commit()
    await upsert_preference(11, "memory_enabled", "false", async_db_session)

    # Seed a fact
    async_db_session.add(
        MemoryFact(
            user_id=11,
            fact_text="User drinks coffee",
            embedding=[0.5] * 1536,
            source_session_id="seed",
        )
    )
    await async_db_session.commit()

    mock_client = MagicMock()
    mock_embed = AsyncMock()
    mock_client.embeddings.create = mock_embed
    monkeypatch.setattr(memory_mod, "_get_openai_client", lambda: mock_client)

    results = await memory_mod.retrieve_relevant_memories(
        user_id=11,
        query_text="coffee",
        db_session=async_db_session,
    )

    assert results == []
    mock_embed.assert_not_called()


async def test_session_state_includes_memories(async_db_session, monkeypatch):
    """initialize_session_state includes user_memories when memory_enabled=True, [] when False."""
    from unittest.mock import AsyncMock, MagicMock

    import fakeredis.aioredis

    from daily.db.models import MemoryFact
    from daily.profile import memory as memory_mod
    from daily.profile.service import _ensure_default_user, upsert_preference

    await _ensure_default_user(12, async_db_session)
    await async_db_session.commit()
    # Ensure memory_enabled=True (may have been set False in a previous test run)
    await upsert_preference(12, "memory_enabled", "true", async_db_session)

    # Seed two facts
    embedding = [0.3] * 1536
    async_db_session.add(
        MemoryFact(
            user_id=12,
            fact_text="User has a standing Monday meeting",
            embedding=embedding,
            source_session_id="seed-s1",
        )
    )
    async_db_session.add(
        MemoryFact(
            user_id=12,
            fact_text="User prefers formal tone",
            embedding=[0.4] * 1536,
            source_session_id="seed-s2",
        )
    )
    await async_db_session.commit()

    mock_client = MagicMock()
    mock_embed = AsyncMock(
        return_value=MagicMock(data=[MagicMock(embedding=embedding)])
    )
    mock_client.embeddings.create = mock_embed
    monkeypatch.setattr(memory_mod, "_get_openai_client", lambda: mock_client)

    fake_redis = fakeredis.aioredis.FakeRedis()

    from daily.orchestrator.session import initialize_session_state

    state = await initialize_session_state(
        user_id=12,
        redis=fake_redis,
        db_session=async_db_session,
    )

    assert "user_memories" in state
    assert isinstance(state["user_memories"], list)
    assert len(state["user_memories"]) >= 1

    # Now test with memory_enabled=False
    await upsert_preference(12, "memory_enabled", "false", async_db_session)

    state_disabled = await initialize_session_state(
        user_id=12,
        redis=fake_redis,
        db_session=async_db_session,
    )
    assert state_disabled["user_memories"] == []


# ---------------------------------------------------------------------------
# Wave 2 (Plan 04) — trigger wiring
# ---------------------------------------------------------------------------


async def test_no_hallucination_loop(async_db_session, monkeypatch):
    """Dedup prevents re-insertion of facts the system itself recalled and injected.

    T-09-16 mitigation: session_history only contains user+assistant turns from the
    conversation, never the injected state.user_memories. This test verifies that
    even if the LLM hallucinates and returns a fact matching an already-stored one,
    the cosine-distance dedup guard (Plan 02) blocks the duplicate insert.

    Scenario 1: LLM returns no new facts (clean session) — row count unchanged.
    Scenario 2: LLM hallucinates and returns the pre-seeded fact — dedup fires,
                row count still 1.
    """
    from unittest.mock import AsyncMock, MagicMock

    from sqlalchemy import func, select

    from daily.db.models import MemoryFact
    from daily.profile import memory as memory_mod
    from daily.profile.service import _ensure_default_user

    # Use a dedicated user_id to avoid cross-test contamination
    USER_ID = 20
    SEEDED_EMBEDDING = [0.7] * 1536
    SEEDED_FACT = "User travels frequently"

    # Seed one MemoryFact row
    await _ensure_default_user(USER_ID, async_db_session)
    await async_db_session.commit()
    seeded = MemoryFact(
        user_id=USER_ID,
        fact_text=SEEDED_FACT,
        embedding=SEEDED_EMBEDDING,
        source_session_id="seed-hallucination",
    )
    async_db_session.add(seeded)
    await async_db_session.commit()

    # Helper: count MemoryFact rows for USER_ID
    async def _count_rows() -> int:
        result = await async_db_session.execute(
            select(func.count()).select_from(MemoryFact).where(MemoryFact.user_id == USER_ID)
        )
        return result.scalar_one()

    assert await _count_rows() == 1

    # --- Scenario 1: LLM returns no new facts (no hallucination) ---
    mock_client_1 = MagicMock()
    mock_client_1.chat.completions.create = AsyncMock(
        return_value=MagicMock(
            choices=[MagicMock(message=MagicMock(content='{"facts": []}'))]
        )
    )
    mock_client_1.embeddings.create = AsyncMock(
        return_value=MagicMock(data=[MagicMock(embedding=[0.1] * 1536)])
    )
    monkeypatch.setattr(memory_mod, "_get_openai_client", lambda: mock_client_1)

    session_history = [
        {"role": "user", "content": "Just confirming the meeting time"},
        {"role": "assistant", "content": "Meeting is at 10am"},
    ]
    await memory_mod.extract_and_store_memories(
        user_id=USER_ID,
        session_history=session_history,
        session_id="s-hallucination-1",
        db_session=async_db_session,
    )

    assert await _count_rows() == 1, "Scenario 1: row count must remain 1 when LLM returns no facts"

    # --- Scenario 2: LLM hallucinates and returns the already-stored fact ---
    mock_client_2 = MagicMock()
    mock_client_2.chat.completions.create = AsyncMock(
        return_value=MagicMock(
            choices=[
                MagicMock(
                    message=MagicMock(
                        content=f'{{"facts": ["{SEEDED_FACT}"]}}'
                    )
                )
            ]
        )
    )
    # _embed returns the same vector as the seeded row — cosine distance = 0
    mock_client_2.embeddings.create = AsyncMock(
        return_value=MagicMock(data=[MagicMock(embedding=SEEDED_EMBEDDING)])
    )
    monkeypatch.setattr(memory_mod, "_get_openai_client", lambda: mock_client_2)

    await memory_mod.extract_and_store_memories(
        user_id=USER_ID,
        session_history=session_history,
        session_id="s-hallucination-2",
        db_session=async_db_session,
    )

    # Dedup must block the re-insertion — row count still 1
    assert await _count_rows() == 1, (
        "Scenario 2: dedup must prevent re-insertion of hallucinated fact "
        f"'{SEEDED_FACT}' that matches the seeded embedding"
    )


# ---------------------------------------------------------------------------
# Phase 10: Memory transparency helpers (MEM-01, MEM-02, MEM-03)
# ---------------------------------------------------------------------------


async def _clear_user_facts(user_id: int, session) -> None:
    """Helper: delete all MemoryFact rows for a user to ensure clean test state."""
    from sqlalchemy import delete as sa_delete

    from daily.db.models import MemoryFact

    await session.execute(sa_delete(MemoryFact).where(MemoryFact.user_id == user_id))
    await session.commit()


async def test_list_all_memories_returns_facts(async_db_session, monkeypatch):
    """list_all_memories returns fact_text strings for all stored facts."""
    from daily.db.models import MemoryFact
    from daily.profile import memory as memory_mod
    from daily.profile.service import _ensure_default_user

    USER_ID = 30
    await _ensure_default_user(USER_ID, async_db_session)
    await async_db_session.commit()
    await _clear_user_facts(USER_ID, async_db_session)

    for i in range(3):
        async_db_session.add(
            MemoryFact(
                user_id=USER_ID,
                fact_text=f"test fact {i + 1}",
                embedding=[0.0] * 1536,
                source_session_id="test-session",
            )
        )
    await async_db_session.commit()

    results = await memory_mod.list_all_memories(USER_ID, async_db_session)

    assert isinstance(results, list)
    assert len(results) == 3
    for r in results:
        assert isinstance(r, str)


async def test_list_all_memories_respects_limit(async_db_session, monkeypatch):
    """list_all_memories returns at most `limit` facts."""
    from daily.db.models import MemoryFact
    from daily.profile import memory as memory_mod
    from daily.profile.service import _ensure_default_user

    USER_ID = 31
    await _ensure_default_user(USER_ID, async_db_session)
    await async_db_session.commit()
    await _clear_user_facts(USER_ID, async_db_session)

    for i in range(5):
        async_db_session.add(
            MemoryFact(
                user_id=USER_ID,
                fact_text=f"fact {i + 1}",
                embedding=[0.0] * 1536,
                source_session_id="test-session",
            )
        )
    await async_db_session.commit()

    results = await memory_mod.list_all_memories(USER_ID, async_db_session, limit=2)

    assert len(results) == 2


async def test_list_all_memories_empty(async_db_session, monkeypatch):
    """list_all_memories returns [] for user with no stored facts."""
    from daily.profile import memory as memory_mod
    from daily.profile.service import _ensure_default_user

    USER_ID = 32
    await _ensure_default_user(USER_ID, async_db_session)
    await async_db_session.commit()
    await _clear_user_facts(USER_ID, async_db_session)

    results = await memory_mod.list_all_memories(USER_ID, async_db_session)

    assert results == []


async def test_list_all_memories_bypasses_memory_enabled(async_db_session, monkeypatch):
    """list_all_memories returns facts even when memory_enabled=False."""
    from daily.db.models import MemoryFact
    from daily.profile import memory as memory_mod
    from daily.profile.service import _ensure_default_user, upsert_preference

    USER_ID = 33
    await _ensure_default_user(USER_ID, async_db_session)
    await async_db_session.commit()
    await _clear_user_facts(USER_ID, async_db_session)
    await upsert_preference(USER_ID, "memory_enabled", "false", async_db_session)

    async_db_session.add(
        MemoryFact(
            user_id=USER_ID,
            fact_text="should still be visible",
            embedding=[0.0] * 1536,
            source_session_id="test-session",
        )
    )
    await async_db_session.commit()

    results = await memory_mod.list_all_memories(USER_ID, async_db_session)

    assert len(results) == 1
    assert results[0] == "should still be visible"


async def test_list_all_memories_orders_by_created_at_desc(async_db_session, monkeypatch):
    """list_all_memories returns most recently inserted facts first."""
    from daily.db.models import MemoryFact
    from daily.profile import memory as memory_mod
    from daily.profile.service import _ensure_default_user

    USER_ID = 34
    await _ensure_default_user(USER_ID, async_db_session)
    await async_db_session.commit()
    await _clear_user_facts(USER_ID, async_db_session)

    # Insert facts in order — DB auto-timestamps created_at
    for i in range(3):
        async_db_session.add(
            MemoryFact(
                user_id=USER_ID,
                fact_text=f"fact inserted {i + 1}",
                embedding=[0.0] * 1536,
                source_session_id="test-session",
            )
        )
        await async_db_session.commit()

    results = await memory_mod.list_all_memories(USER_ID, async_db_session)

    # Most recently inserted row should be first (created_at desc)
    assert results[0] == "fact inserted 3"
    assert results[-1] == "fact inserted 1"


async def test_delete_memory_fact_removes_closest_match(async_db_session, monkeypatch):
    """delete_memory_fact deletes the closest matching fact and returns its text."""
    from unittest.mock import AsyncMock, MagicMock

    from sqlalchemy import func, select

    from daily.db.models import MemoryFact
    from daily.profile import memory as memory_mod
    from daily.profile.service import _ensure_default_user

    USER_ID = 35
    EMBEDDING = [1.0] + [0.0] * 1535

    await _ensure_default_user(USER_ID, async_db_session)
    await async_db_session.commit()
    await _clear_user_facts(USER_ID, async_db_session)

    async_db_session.add(
        MemoryFact(
            user_id=USER_ID,
            fact_text="fact to be deleted",
            embedding=EMBEDDING,
            source_session_id="test-session",
        )
    )
    await async_db_session.commit()

    # Mock embedding to return the same vector — cosine distance = 0 (well below 0.2)
    mock_client = AsyncMock()
    mock_client.embeddings.create = AsyncMock(
        return_value=MagicMock(data=[MagicMock(embedding=EMBEDDING)])
    )
    monkeypatch.setattr(memory_mod, "_get_openai_client", lambda: mock_client)

    result = await memory_mod.delete_memory_fact(USER_ID, "fact to be deleted", async_db_session)

    assert result == "fact to be deleted"

    # Verify the row is actually gone
    count_result = await async_db_session.execute(
        select(func.count()).select_from(MemoryFact).where(MemoryFact.user_id == USER_ID)
    )
    assert count_result.scalar_one() == 0


async def test_delete_memory_fact_no_match(async_db_session, monkeypatch):
    """delete_memory_fact returns None when no fact is within the threshold."""
    from unittest.mock import AsyncMock, MagicMock

    from daily.db.models import MemoryFact
    from daily.profile import memory as memory_mod
    from daily.profile.service import _ensure_default_user

    USER_ID = 36
    # Insert a fact at one end of the embedding space
    await _ensure_default_user(USER_ID, async_db_session)
    await async_db_session.commit()
    await _clear_user_facts(USER_ID, async_db_session)

    async_db_session.add(
        MemoryFact(
            user_id=USER_ID,
            fact_text="some distant fact",
            embedding=[1.0] + [0.0] * 1535,
            source_session_id="test-session",
        )
    )
    await async_db_session.commit()

    # Mock embedding to return orthogonal vector — cosine distance ~1.0 (> 0.2 threshold)
    orthogonal_embedding = [0.0] * 1535 + [1.0]
    mock_client = AsyncMock()
    mock_client.embeddings.create = AsyncMock(
        return_value=MagicMock(data=[MagicMock(embedding=orthogonal_embedding)])
    )
    monkeypatch.setattr(memory_mod, "_get_openai_client", lambda: mock_client)

    result = await memory_mod.delete_memory_fact(USER_ID, "completely different topic", async_db_session)

    assert result is None


async def test_delete_memory_fact_bypasses_memory_enabled(async_db_session, monkeypatch):
    """delete_memory_fact works even when memory_enabled=False."""
    from unittest.mock import AsyncMock, MagicMock

    from daily.db.models import MemoryFact
    from daily.profile import memory as memory_mod
    from daily.profile.service import _ensure_default_user, upsert_preference

    USER_ID = 37
    EMBEDDING = [1.0] + [0.0] * 1535

    await _ensure_default_user(USER_ID, async_db_session)
    await async_db_session.commit()
    await _clear_user_facts(USER_ID, async_db_session)
    await upsert_preference(USER_ID, "memory_enabled", "false", async_db_session)

    async_db_session.add(
        MemoryFact(
            user_id=USER_ID,
            fact_text="fact deletable even when disabled",
            embedding=EMBEDDING,
            source_session_id="test-session",
        )
    )
    await async_db_session.commit()

    mock_client = AsyncMock()
    mock_client.embeddings.create = AsyncMock(
        return_value=MagicMock(data=[MagicMock(embedding=EMBEDDING)])
    )
    monkeypatch.setattr(memory_mod, "_get_openai_client", lambda: mock_client)

    result = await memory_mod.delete_memory_fact(USER_ID, "fact deletable even when disabled", async_db_session)

    assert result == "fact deletable even when disabled"


async def test_clear_all_memories_deletes_all(async_db_session, monkeypatch):
    """clear_all_memories deletes all facts and returns the count."""
    from sqlalchemy import func, select

    from daily.db.models import MemoryFact
    from daily.profile import memory as memory_mod
    from daily.profile.service import _ensure_default_user

    USER_ID = 38
    await _ensure_default_user(USER_ID, async_db_session)
    await async_db_session.commit()
    await _clear_user_facts(USER_ID, async_db_session)

    for i in range(3):
        async_db_session.add(
            MemoryFact(
                user_id=USER_ID,
                fact_text=f"fact {i + 1}",
                embedding=[0.0] * 1536,
                source_session_id="test-session",
            )
        )
    await async_db_session.commit()

    count = await memory_mod.clear_all_memories(USER_ID, async_db_session)

    assert count == 3

    remaining = await async_db_session.execute(
        select(func.count()).select_from(MemoryFact).where(MemoryFact.user_id == USER_ID)
    )
    assert remaining.scalar_one() == 0


async def test_clear_all_memories_returns_zero_when_empty(async_db_session, monkeypatch):
    """clear_all_memories returns 0 when user has no stored facts."""
    from daily.profile import memory as memory_mod
    from daily.profile.service import _ensure_default_user

    USER_ID = 39
    await _ensure_default_user(USER_ID, async_db_session)
    await async_db_session.commit()
    await _clear_user_facts(USER_ID, async_db_session)

    count = await memory_mod.clear_all_memories(USER_ID, async_db_session)

    assert count == 0


async def test_clear_all_memories_scoped_to_user(async_db_session, monkeypatch):
    """clear_all_memories only deletes facts for the specified user."""
    from sqlalchemy import func, select

    from daily.db.models import MemoryFact
    from daily.profile import memory as memory_mod
    from daily.profile.service import _ensure_default_user

    USER_1 = 40
    USER_2 = 41

    await _ensure_default_user(USER_1, async_db_session)
    await _ensure_default_user(USER_2, async_db_session)
    await async_db_session.commit()
    await _clear_user_facts(USER_1, async_db_session)
    await _clear_user_facts(USER_2, async_db_session)

    # Insert facts for both users
    for i in range(2):
        async_db_session.add(
            MemoryFact(
                user_id=USER_1,
                fact_text=f"user1 fact {i + 1}",
                embedding=[0.0] * 1536,
                source_session_id="test-session",
            )
        )
    async_db_session.add(
        MemoryFact(
            user_id=USER_2,
            fact_text="user2 fact 1",
            embedding=[0.0] * 1536,
            source_session_id="test-session",
        )
    )
    await async_db_session.commit()

    # Clear only user 1
    count = await memory_mod.clear_all_memories(USER_1, async_db_session)
    assert count == 2

    # User 2's facts should remain
    remaining = await async_db_session.execute(
        select(func.count()).select_from(MemoryFact).where(MemoryFact.user_id == USER_2)
    )
    assert remaining.scalar_one() == 1

    # User 1's facts should be gone
    user1_remaining = await async_db_session.execute(
        select(func.count()).select_from(MemoryFact).where(MemoryFact.user_id == USER_1)
    )
    assert user1_remaining.scalar_one() == 0
