# Phase 7: Tech Debt Fixes - Discussion Log

**Date:** 2026-04-15
**Phase:** 07-tech-debt-fixes
**Mode:** discuss

## Gray Areas Presented & Decisions

| Area | Decision |
|------|----------|
| FIX-01 direct-recipient semantics | Exact match in To only (CC/BCC → WEIGHT_CC) |
| FIX-02 Slack pagination stop condition | Bounded by 24h briefing time window |
| FIX-03 message_id source | Briefing metadata cached in session state |
| Testing / backfill | Unit tests per fix + backfill historical signals + clean iCloud duplicate files |

## Notes

- User selected time-window pagination rather than page cap — aligns with briefing being a rolling 24h window anyway.
- Backfill was approved because Phase 8 (adaptive ranker) depends on clean signal data.
- iCloud duplicate cleanup is roadmap-adjacent but user explicitly folded into scope.
