# Phase 10: Memory Transparency - Discussion Log (Assumptions Mode)

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions captured in CONTEXT.md — this log preserves the analysis.

**Date:** 2026-04-18
**Phase:** 10-memory-transparency
**Mode:** assumptions
**Areas analyzed:** Intent Routing, Memory Introspection, Fact Deletion & Bulk Clear, memory_enabled Flag, Approval Gate

## Assumptions Presented

### Intent Routing & Memory Query Handling
| Assumption | Confidence | Evidence |
|------------|-----------|----------|
| Add memory keywords to route_intent() in graph.py; new node routes all three memory operations | Confident | `src/daily/orchestrator/graph.py:32–71` — keyword whitelist routing for all intents |

### Memory Introspection Node
| Assumption | Confidence | Evidence |
|------------|-----------|----------|
| New memory_node calls retrieve_relevant_memories() with broad synthetic query; no LLM re-summarisation | Likely | `src/daily/profile/memory.py:245–294` — retrieve returns list[str]; `state.py:55` — user_memories already in SessionState |

### Fact Deletion & Bulk Clear
| Assumption | Confidence | Evidence |
|------------|-----------|----------|
| Deletion via cosine similarity match (threshold 0.2) then DELETE; bulk clear via DELETE WHERE user_id | Likely | `src/daily/db/models.py` — MemoryFact ORM + HNSW index; dedup threshold 0.1 at `memory.py:106` |

### memory_enabled Flag as Sole Control
| Assumption | Confidence | Evidence |
|------------|-----------|----------|
| Disable = upsert_preference(memory_enabled=False); no migration needed | Confident | `src/daily/profile/models.py:55` — field exists; extraction/retrieval gates at `memory.py:173–178`, `270–275` |

### No Approval Gate for Memory Commands
| Assumption | Confidence | Evidence |
|------------|-----------|----------|
| Memory commands execute immediately (no interrupt); approval reserved for external actions | Likely | `src/daily/orchestrator/nodes.py:593–650` — interrupt() only for draft/send/schedule |

## Corrections Made

No corrections — all assumptions confirmed by user.

## External Research Topics (not resolved — scoped to Claude's discretion)

- Cosine threshold for deletion matching (0.2 selected as reasonable starting point; empirical tuning deferred)
- Fact summarisation approach for voice response (list read-back chosen for latency; LLM prose deferred to Phase 12)
- Max facts per user policy (deferred to v2.0)
