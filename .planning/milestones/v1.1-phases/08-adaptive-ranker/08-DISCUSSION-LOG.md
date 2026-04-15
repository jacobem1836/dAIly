# Phase 8: Adaptive Ranker - Discussion Log (Discuss Mode)

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions captured in CONTEXT.md — this log preserves the discussion.

**Date:** 2026-04-15
**Phase:** 08-adaptive-ranker
**Mode:** discuss
**Areas analyzed:** Scoring model, Signal weighting, What gets learned, Graceful degradation

## Assumptions Presented

### Scoring model
| Assumption | Confidence | Evidence |
|------------|-----------|----------|
| Blended alpha (0.2/0.8 until 30+ signals) | Confirmed | STATE.md pending todo — confirmed by user |
| Linear alpha growth capped at 0.8 | Confirmed | User selected recommended default |

### Signal weighting
| Assumption | Confidence | Evidence |
|------------|-----------|----------|
| Tiered weights: expand/re_request=+2, follow_up=+1, skip=-2, correction=0 | Confirmed | User selected recommended default |
| Last 30 signals per sender rolling window | Confirmed | User selected recommended default |

### What gets learned
| Assumption | Confidence | Evidence |
|------------|-----------|----------|
| Sender weight only replaced | Confirmed | User selected recommended default |
| VIP override bypasses blend | Carried forward | Existing ranker behaviour, preserved |

### Graceful degradation
| Assumption | Confidence | Evidence |
|------------|-----------|----------|
| Silent fallback to heuristics, log warning | Confirmed | User selected recommended default |

## Corrections Made

No corrections — all assumptions confirmed.

## Deferred Ideas

- Keyword weight learning — future intelligence phase
- Recency decay personalisation — future phase
- Per-sender score explanation UI — Phase 10 (Memory Transparency)
