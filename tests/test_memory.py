"""Phase 9 memory module tests (INTEL-02).

Wave 0 scaffold — tests are marked skip until their implementation lands:
  - test_extract_facts_stores_embedding (Plan 02)
  - test_extraction_skipped_when_disabled (Plan 02)
  - test_dedup_prevents_duplicate_insert (Plan 02)
  - test_retrieve_relevant_facts (Plan 03)
  - test_retrieval_skipped_when_disabled (Plan 03)
  - test_session_state_includes_memories (Plan 03)
  - test_extraction_swallows_errors (Plan 02)
  - test_no_hallucination_loop (Plan 04)
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
# Wave 1 (Plan 02) — extraction stubs
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="pending Plan 02 implementation")
async def test_extract_facts_stores_embedding():
    raise NotImplementedError


@pytest.mark.skip(reason="pending Plan 02 implementation")
async def test_extraction_skipped_when_disabled():
    raise NotImplementedError


@pytest.mark.skip(reason="pending Plan 02 implementation")
async def test_dedup_prevents_duplicate_insert():
    raise NotImplementedError


@pytest.mark.skip(reason="pending Plan 02 implementation")
async def test_extraction_swallows_errors():
    raise NotImplementedError


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
