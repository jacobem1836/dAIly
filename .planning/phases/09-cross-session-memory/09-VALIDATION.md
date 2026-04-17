---
phase: 9
slug: cross-session-memory
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-17
---

# Phase 9 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio |
| **Config file** | pytest.ini or pyproject.toml [tool.pytest] |
| **Quick run command** | `uv run pytest tests/test_memory.py -x -q` |
| **Full suite command** | `uv run pytest tests/ -x -q` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_memory.py -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -x -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 9-01-01 | 01 | 0 | INTEL-02 | — | N/A | infra | `uv run pytest tests/test_memory.py --collect-only` | ❌ W0 | ⬜ pending |
| 9-01-02 | 01 | 1 | INTEL-02 | — | N/A | unit | `uv run pytest tests/test_memory.py::test_migration_creates_table -x` | ✅ | ⬜ pending |
| 9-02-01 | 02 | 1 | INTEL-02 | — | N/A | unit | `uv run pytest tests/test_memory.py::test_extract_facts_stores_embedding -x` | ✅ | ⬜ pending |
| 9-02-02 | 02 | 1 | INTEL-02 | — | Extraction skipped when memory_enabled=False | unit | `uv run pytest tests/test_memory.py::test_extraction_skipped_when_disabled -x` | ✅ | ⬜ pending |
| 9-02-03 | 02 | 1 | INTEL-02 | — | Dedup prevents near-duplicate facts | unit | `uv run pytest tests/test_memory.py::test_dedup_prevents_duplicate_insert -x` | ✅ | ⬜ pending |
| 9-03-01 | 03 | 2 | INTEL-02 | — | N/A | unit | `uv run pytest tests/test_memory.py::test_retrieve_relevant_facts -x` | ✅ | ⬜ pending |
| 9-03-02 | 03 | 2 | INTEL-02 | — | Retrieval skipped when memory_enabled=False | unit | `uv run pytest tests/test_memory.py::test_retrieval_skipped_when_disabled -x` | ✅ | ⬜ pending |
| 9-04-01 | 04 | 2 | INTEL-02 | — | No re-extraction of injected facts | unit | `uv run pytest tests/test_memory.py::test_no_hallucination_loop -x` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_memory.py` — stubs for INTEL-02 (extraction, dedup, retrieval, gating)
- [ ] `tests/conftest.py` — async DB fixture if not already present

*Existing pytest-asyncio infrastructure covers the framework requirement.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Memory appears in next-morning briefing context after voice session | INTEL-02 | Requires a full pipeline run with real data | Run voice session, state a fact, wait for next briefing run, check briefing text reflects the fact |
| Extraction fires non-blocking (voice response not delayed) | INTEL-02 | Timing hard to assert in unit tests | Measure voice loop response time with and without extraction task |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
