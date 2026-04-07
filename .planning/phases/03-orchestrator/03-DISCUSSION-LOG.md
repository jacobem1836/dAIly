# Phase 03: Orchestrator - Discussion Log (Assumptions Mode)

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions captured in CONTEXT.md — this log preserves the analysis.

**Date:** 2026-04-07
**Phase:** 03-orchestrator
**Mode:** assumptions
**Areas analyzed:** LLM Orchestration Framework, User Profile & Preferences, Interaction Signal Capture, In-Session Context & Thread Summarisation, Integration with Existing Pipeline

## Assumptions Presented

### LLM Orchestration Framework
| Assumption | Confidence | Evidence |
|------------|-----------|----------|
| Use LangGraph 1.0+ as orchestration backbone with AsyncPostgresSaver checkpointer | Confident | CLAUDE.md recommendation, LangGraph 1.0 stable release (Oct 2025), native async + FastAPI support |
| Dual-model routing via per-node instantiation (GPT-4.1 + GPT-4.1 mini) | Confident | LangGraph natively supports per-node model assignment, CLAUDE.md multi-model strategy |

### User Profile & Preferences (PERS-01)
| Assumption | Confidence | Evidence |
|------------|-----------|----------|
| JSONB user_profile table, skip mem0 for Phase 3 | Likely | Phase 2 BriefingConfig DB pattern, PERS-01 preferences are explicit not conversation-emergent |

### Interaction Signal Capture (PERS-02)
| Assumption | Confidence | Evidence |
|------------|-----------|----------|
| Append-only signal_log table with enum signal types | Likely | PERS-02 "stored for future ranking use", aligns with Phase 4 action_log pattern |

### In-Session Context & Thread Summarisation (BRIEF-07)
| Assumption | Confidence | Evidence |
|------------|-----------|----------|
| In-memory session state via LangGraph checkpointer, on-demand thread fetch + GPT-4.1 mini summarisation | Likely | Phase 2 Redis cache pattern, existing get_email_body() adapter, redactor reuse |

### Integration with Existing Pipeline
| Assumption | Confidence | Evidence |
|------------|-----------|----------|
| Orchestrator consumes Redis-cached briefing, does not re-run pipeline | Confident | Phase 2 BRIEF-01 <1s delivery requirement, BriefingOutput model established |

## Corrections Made

No corrections — all assumptions confirmed.

## External Research

- LangGraph stability: 1.0+ stable since Oct 2025, zero breaking changes until 2.0. Pin `langgraph>=1.0.3`. (Source: LangChain blog, Medium)
- mem0 scope: Valuable for conversation-emergent preferences but overkill when preferences are explicit CLI config. Start with JSONB, upgrade later if needed. (Source: mem0.ai docs, Context7)
- Dual-model routing: LangGraph supports per-node model instantiation natively. No wrapper needed. (Source: LangGraph docs, multiple tutorials)
