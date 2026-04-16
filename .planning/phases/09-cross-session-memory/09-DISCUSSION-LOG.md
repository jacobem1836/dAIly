# Phase 9: Cross-Session Memory — Discussion Log (Assumptions Mode)

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions captured in CONTEXT.md — this log preserves the analysis.

**Date:** 2026-04-16
**Phase:** 09-cross-session-memory
**Mode:** assumptions
**Areas analyzed:** Memory Library, Extraction Trigger, Hallucination Loop Prevention, `memory_enabled` Flag, Briefing Injection Point

## Assumptions Presented

### Memory Library
| Assumption | Confidence | Evidence |
|------------|-----------|----------|
| Custom extraction pipeline (no mem0/langmem), OpenAI text-embedding-3-small, new memory_facts table with VECTOR(1536) | Likely | No mem0/langmem in pyproject.toml; STATE.md note re langmem compatibility unverified; Phase 10 needs row-level access |

### Extraction Trigger
| Assumption | Confidence | Evidence |
|------------|-----------|----------|
| asyncio.create_task() in run_voice_session() finally block in voice/loop.py | Confident | _capture_signal() and _log_action() in nodes.py use same pattern; Phase 8 CONTEXT.md explicitly states this approach |

### Hallucination Loop Prevention
| Assumption | Confidence | Evidence |
|------------|-----------|----------|
| Vector similarity dedup before insert (cosine distance < 0.1) | Unclear | No existing dedup mechanism; two alternatives existed |

### `memory_enabled` Flag
| Assumption | Confidence | Evidence |
|------------|-----------|----------|
| Boolean in UserPreferences JSONB, default True, gates both extraction and injection | Confident | All preference flags (tone, briefing_length, rejection_behaviour) use same JSONB pattern in profile/models.py |

### Briefing Injection Point
| Assumption | Confidence | Evidence |
|------------|-----------|----------|
| Inject at narrator system prompt (precomputed briefing) AND SessionState (live sessions) | Likely | build_narrator_system_prompt() shows preamble pattern; initialize_session_state() is the live session init point |

## Corrections Made

No corrections — all assumptions confirmed by user.

## External Research Flagged

- pgvector Python/SQLAlchemy 2.0 async integration (column type, index choice, query operators)
- OpenAI embedding model dimensionality (text-embedding-3-small at 1536d confirmed as default)
- mem0 vs langmem vs custom — resolved by decision to go custom (Phase 10 row-level access requirement)
