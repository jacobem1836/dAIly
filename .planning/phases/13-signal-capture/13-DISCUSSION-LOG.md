# Phase 13: Signal Capture - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions captured in CONTEXT.md — this log preserves the discussion.

**Date:** 2026-04-18
**Phase:** 13-signal-capture
**Mode:** discuss
**Areas discussed:** Skip trigger, Item tracking, Decay formula, Re-request handling

## Gray Areas Presented

| Area | Options offered |
|------|----------------|
| Skip trigger | Explicit only / Both explicit + implicit / Implicit only |
| Item tracking | Structured Redis data / Parse section headers / Cursor approximation |
| Decay formula | Exponential decay 30-day / Count-based 30-day / Exponential all-time |
| Re-request handling | New re_request_node / Inline in respond_node / Handle in voice loop |

## Decisions Made

### Skip trigger
- **Chosen:** Both explicit + implicit
- Explicit: "skip"/"next"/"move on" → skip intent route in orchestrator
- Implicit: barge-in + silence > 2s → voice loop fires inline

### Item tracking
- **Chosen:** Structured data in Redis
- At precompute time, write `briefing:{user_id}_items` JSON list alongside narrative
- Format: [{item_id, type, target_id, sentence_range_start, sentence_range_end}]
- `SessionState` gains `briefing_items` + `current_item_index` fields

### Decay formula
- **Chosen:** Exponential decay, 30-day window
- `weight = signal_weight * (0.95 ** days_old)`
- Weights: skip=−1.0, re_request=+1.0, expand=+0.5
- Sigmoid output range: [0.5, 2.0] with midpoint parameter 3.0

### Re-request handling
- **Chosen:** New re_request_node in graph
- Mirrors summarise_thread_node pattern
- Re-speaks current item sentences + fires re_request signal with target_id

## Codebase Findings (from scout)

- `adaptive_ranker.py` does not exist — only compiled pycache + import hook in context_builder.py
- `SignalType.skip` and `SignalType.re_request` already in enum — no DB schema changes needed
- No per-item tracking in current briefing delivery — flat string only
- `_capture_signal()` fire-and-forget pattern already established in nodes.py
- `sender_multipliers` hook already wired in context_builder.py line ~181
