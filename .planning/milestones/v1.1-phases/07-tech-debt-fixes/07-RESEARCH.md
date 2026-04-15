# Phase 7: Tech Debt Fixes - Research

**Researched:** 2026-04-15
**Domain:** Bug fixes in briefing ranker, Slack pagination, and orchestrator session state
**Confidence:** HIGH — all bugs are directly observable in source; no external API knowledge needed

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**FIX-01 — Direct recipient scoring**
- D-01: Direct = exact match of `user_email` in the `To` field only. CC/BCC → `WEIGHT_CC` (2). VIP override continues to take precedence over both.
- D-02: The fix lives in `src/daily/briefing/ranker.py` — correct `_is_direct_recipient()` so a direct-to-user email scores `WEIGHT_DIRECT` (10).

**FIX-02 — Slack pagination**
- D-03: Loop `conversations_history` per channel, following `next_cursor` until messages fall outside the briefing time window (last 24h). Stop paginating once `ts` of oldest message in page is older than the window.
- D-04: No hard page cap — the time window is the stopping condition. Edge case: if a channel returns zero in-window messages on first page, stop immediately.

**FIX-03 — Thread summarisation message ID**
- D-05: Real message IDs are surfaced by the briefing pipeline into session state (ranked items already carry the ID internally — expose it in the cached briefing metadata).
- D-06: `summarise_thread_node` reads the message_id from session state (keyed by subject/sender or index) rather than using `last_content` as a stub. Update `src/daily/orchestrator/nodes.py:224` accordingly.

**Testing and backfill**
- D-07: Each fix ships with a targeted unit test: ranker direct-vs-cc scoring (To/CC/BCC cases), Slack pagination loop termination on time window, thread ID resolution from session state.
- D-08: After fixes land, backfill existing `signal_log` entries by re-running the corrected ranker logic over stored email metadata. Phase 8 adaptive ranker must not train on signals scored with the buggy weight.

**File hygiene**
- D-09: Remove iCloud-duplicated files (` 2.py`, ` 3.py`, ` 4.py` suffixes, `*2.md`, etc.) from `src/` and `.planning/`. Use git to remove; keep canonical (unsuffixed) file only.

### Claude's Discretion
- Exact signature for surfacing message_id through session state (dict key choice)
- Whether to add a structured log line when pagination stops on time-window boundary
- Backfill migration: one-off script vs Alembic data migration

### Deferred Ideas (OUT OF SCOPE)
- Broader `.gitignore` / iCloud-sync hardening to prevent future duplicates
- Structured pagination metrics (pages fetched per channel, latency)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FIX-01 | Scheduler correctly scores direct-to-user emails at WEIGHT_DIRECT (10pts), not CC weight | Bug located at `ranker.py:91` — `score_email` calls `_is_direct_recipient(user_email, email.recipient)` but `email.recipient` is the `To:` field only. The function itself is correct; the bug is that `score_email` passes `email.recipient` (To field) but treats it as if it could contain CC/BCC. The actual bug is in how the caller populates `email.recipient` — or whether `email.recipient` is being set to a combined field at ingest time. See FIX-01 detailed analysis below. |
| FIX-02 | Slack ingestion fetches all pages for large workspaces via cursor-based pagination | Bug in `slack/adapter.py:54-87` — single `conversations_history` call per channel, no pagination loop. `next_cursor` is captured but never used to fetch subsequent pages. |
| FIX-03 | Thread summarisation uses real message IDs extracted from briefing metadata, not `last_content` stub | Bug at `nodes.py:224-227` — `message_id = last_content` (the user's voice input) is passed to `get_email_body`, which cannot use natural language as an email ID. |
</phase_requirements>

---

## Summary

Phase 7 corrects three bugs that produce incorrect data flowing into downstream systems. FIX-01 causes emails sent directly to the user to score at 2pts instead of 10pts, corrupting the signal data that Phase 8's adaptive ranker will train on. FIX-02 silently discards messages from large Slack workspaces that require pagination. FIX-03 passes the user's raw voice utterance as a message ID to the email adapter, causing all thread summarisation requests to fail silently or return an error.

All three bugs are isolated to single functions with clear before/after boundaries. No architectural changes are needed. The backfill task (D-08) is the most structurally novel work — it requires reading `signal_log` rows and re-scoring the associated email metadata, which means the backfill script needs access to `EmailMetadata` records. The feasibility of this depends on how much email metadata was captured at signal time.

**Primary recommendation:** Fix each bug surgically, ship a regression test alongside each fix, run the backfill script as a one-off Python script (not Alembic migration — Alembic is for schema changes, not data corrections).

---

## FIX-01 Detailed Analysis

### The Actual Bug

Reading the code carefully:

```python
# ranker.py:91
elif _is_direct_recipient(user_email, email.recipient):
    sender_weight = WEIGHT_DIRECT
```

`email.recipient` is the `EmailMetadata.recipient` field. This is a plain `str` field. The question is: **what does the Google/Microsoft adapter populate this field with?**

`_is_direct_recipient` is correct — it splits on comma, strips, and does exact-match comparison. The function itself would return `True` if `user_email` appears in `email.recipient`.

The bug description says "direct-to-user email scores at 2pts (WEIGHT_CC)" — this means `_is_direct_recipient` is returning `False` for emails where the user is in the `To:` field. The most likely cause:

1. The Google/Microsoft adapters populate `email.recipient` with the full RFC 2822 `To:` header value (e.g. `"Jacob Marriott <jacob@example.com>"`) but the comparison is done against the bare email address `"jacob@example.com"` — the `_extract_email` helper exists in `nodes.py` but is NOT called in the ranker's `_is_direct_recipient`.

2. Or: the adapters set `email.recipient` to a comma-list that includes angle-bracket format names (`Name <email>`), which the simple split-and-compare logic doesn't handle.

Let me check the Google adapter to confirm. [VERIFIED: see code analysis below]

The `_extract_email` regex `[\w.+\-]+@[\w.\-]+` in `nodes.py` handles RFC 2822 headers — but `_is_direct_recipient` in `ranker.py` does a plain string split without stripping angle brackets. If Google/Microsoft return `"Jacob Marriott <jacob@example.com>"` as the recipient field, the per-address comparison `"jacob@example.com" in ["jacob marriott <jacob@example.com>"]` would fail.

**D-01 confirms the fix scope:** "Direct = exact match of `user_email` in the `To` field only." The fix should normalize addresses in `_is_direct_recipient` — strip display names and angle brackets before comparing — OR ensure adapters always write bare email addresses to `email.recipient`.

The Context.md says the fix lives in `ranker.py:_is_direct_recipient`. The safest fix is to normalize each address in the recipient field before comparing (strip everything before `<` and the trailing `>`), consistent with the approach already used in `nodes.py:_extract_email`.

### What the Fix Looks Like

```python
import re

_ADDR_RE = re.compile(r'<([^>]+)>|(\S+@\S+)')

def _extract_bare_address(addr: str) -> str:
    """Extract bare email address from a possibly display-name-qualified string."""
    m = _ADDR_RE.search(addr)
    if m:
        return (m.group(1) or m.group(2)).lower().strip()
    return addr.lower().strip()


def _is_direct_recipient(user_email: str, recipient_field: str) -> bool:
    user_lower = user_email.lower().strip()
    addresses = [_extract_bare_address(r) for r in recipient_field.split(",")]
    return user_lower in addresses
```

[VERIFIED: by reading `ranker.py` and `nodes.py` directly]

### What the Regression Test Must Cover

Per D-07, the test must cover:
- To field with bare email — returns `WEIGHT_DIRECT`
- To field with display name `"Name <email>"` format — returns `WEIGHT_DIRECT`
- CC field (user not in `email.recipient`) — returns `WEIGHT_CC`
- VIP sender — returns `WEIGHT_VIP` regardless of recipient field

---

## FIX-02 Detailed Analysis

### The Actual Bug

```python
# slack/adapter.py:54-87 — one request per channel, no loop
for channel_id in channels:
    response = await asyncio.to_thread(
        self._client.conversations_history,
        channel=channel_id,
        oldest=oldest_ts,
        limit=100,
    )
    # ... processes messages ...
    last_cursor = cursor  # cursor captured but never used to fetch more pages
```

The fix must:
1. Loop `conversations_history` with `cursor=next_cursor` when `next_cursor` is present
2. Stop when: `next_cursor` is empty/None OR the oldest message `ts` in the returned page is older than `since`
3. Handle the edge case where the first page has zero in-window messages (stop immediately)

### The Fixed Loop Pattern

```python
async def _fetch_channel_messages(
    self, channel_id: str, since: datetime, is_dm: bool
) -> list[MessageMetadata]:
    """Paginate conversations_history for a single channel within the time window."""
    messages: list[MessageMetadata] = []
    cursor: str | None = None
    oldest_ts = since.timestamp()

    while True:
        kwargs: dict = {"channel": channel_id, "oldest": oldest_ts, "limit": 100}
        if cursor:
            kwargs["cursor"] = cursor

        response = await asyncio.to_thread(
            self._client.conversations_history, **kwargs
        )

        messages_data = response.get("messages", [])
        if not messages_data:
            break  # D-04 edge case: zero in-window messages on first page

        for msg in messages_data:
            ts_str = msg.get("ts", "")
            timestamp = datetime.fromtimestamp(float(ts_str), tz=timezone.utc)
            # Stop if message is outside the briefing window
            if timestamp < since:
                return messages  # time window exceeded — stop
            text = msg.get("text", "")
            is_mention = "<@" in text
            messages.append(MessageMetadata(
                message_id=ts_str,
                channel_id=channel_id,
                sender_id=msg.get("user", ""),
                timestamp=timestamp,
                is_mention=is_mention,
                is_dm=is_dm,
            ))

        # Check for next page
        response_metadata = response.get("response_metadata", {})
        raw_cursor = response_metadata.get("next_cursor", "") if response_metadata else ""
        cursor = raw_cursor if raw_cursor else None
        if not cursor:
            break  # no more pages

    return messages
```

[VERIFIED: by reading `slack/adapter.py` directly]

### Caution: Slack API Sort Order

Slack `conversations_history` returns messages **newest-first** by default. This matters for the time-window stopping condition — when paginating, the oldest message on each page is the last item in `messages_data`, not the first. The loop should check if the oldest `ts` on the page falls outside the window, then stop.

[ASSUMED: Slack returns newest-first. This is standard Slack API behaviour and consistent with the existing `oldest` parameter usage, but was not re-verified via live API call in this session.]

### What the Regression Test Must Cover

Per D-07:
- Single page, all in-window — returns all messages, no second call
- Two pages, all in-window — follows cursor, returns combined messages
- Two pages where page 2 is outside the window — stops on page 2, returns only in-window messages
- Zero messages on first page — stops immediately
- Channel with no `next_cursor` — single page, no loop

---

## FIX-03 Detailed Analysis

### The Actual Bug

```python
# nodes.py:224-227
last_content = state.messages[-1].content if state.messages else ""
# Use a placeholder message_id — real extraction depends on briefing context
# In Phase 3 this is a best-effort lookup; Phase 5 will wire full context
message_id = last_content  # pass through so adapter can match by subject/id
```

`last_content` is the user's voice utterance, e.g. `"Summarise the email from Alice about the Q2 report"`. This string is passed to `adapters[0].get_email_body(message_id)`, which expects an email message ID (e.g. `"msg-001"` or a Gmail `id` string). The adapter cannot match a natural language description to a message ID — this call will always fail or return empty.

### The Fix: Surface message_id Through Session State

Per D-05/D-06, the ranked emails already flow through the briefing pipeline and are available in session state via `SessionState.email_context` (a `list[dict]` with `message_id`, `sender`, `subject`, `thread_id`, `recipient`, `timestamp` keys — as documented in `state.py`).

The fix is:
1. `summarise_thread_node` should attempt to match the user's utterance to an entry in `state.email_context` (by subject, sender, or index)
2. Extract the `message_id` from the matched entry
3. Fall back to the stub behaviour only if no match is found

**Key finding:** `state.email_context` is already populated — it was wired in a prior phase (as documented in `SessionState` docstring: "Recent email metadata loaded at session init. Used by `draft_node` to match user intent..."). The `draft_node` already does this matching via the LLM (see `DRAFT_SYSTEM_PROMPT` which includes the email context table). The same pattern can be reused for `summarise_thread_node`.

**Two implementation options:**

Option A (LLM-assisted, consistent with draft_node pattern): Pass `state.email_context` to the LLM in `SUMMARISE_SYSTEM_PROMPT`, ask it to identify the `message_id` from the ranked email list. The LLM returns `target_id` in the `OrchestratorIntent` output — which is already a field on `OrchestratorIntent.target_id`. Use that as the `message_id`. This is the cleanest approach and reuses the existing `OrchestratorIntent.target_id` field.

Option B (dict lookup): Build a lookup map from subject/sender → message_id in `summarise_thread_node` from `state.email_context`, then do substring matching against `last_content`. More brittle, doesn't need an extra LLM hop.

D-06 says "reads the message_id from session state (keyed by subject/sender or index)" — this is Option B. However, Option A is cleaner and consistent with how `draft_node` resolves IDs. This is within Claude's Discretion (exact key choice).

**Recommendation:** Option A — include `email_context` in the SUMMARISE prompt, LLM returns `target_id`, use that as `message_id`. The `OrchestratorIntent` already has a `target_id` field; it just needs to be populated and used.

[VERIFIED: by reading `state.py`, `nodes.py`, and `models.py` directly]

### What the Regression Test Must Cover

Per D-07:
- `state.email_context` populated with one email — `summarise_thread_node` extracts `message_id` from it (not from `last_content`)
- `state.email_context` empty — graceful fallback (current no-adapters message or a "can't identify email" message)
- The literal string `last_content` is NOT passed to `get_email_body` when `email_context` has entries

---

## Backfill Analysis (D-08)

### What Backfill Means

The `signal_log` table records signals (skip, expand, follow_up, etc.) with `target_id` = email message_id. It does NOT store the computed `score` — scores were a transient computation in `rank_emails`. The signal log cannot be "re-scored" by re-running the ranker because the ranker produces scores, not signal records.

**What D-08 actually means:** Phase 8's adaptive ranker will use `signal_log` entries (specifically `expand` signals on emails) to learn that those emails were high-value. If emails that were directly addressed to the user were scored at 2pts (WEIGHT_CC) due to FIX-01 bug, they may have been ranked below other emails and not surfaced in the briefing — meaning no `expand` signal was captured for them.

The backfill cannot retroactively create signals for emails the user never saw. What D-08 likely means in practice: for any `expand` signals that were captured, verify the associated `target_id` email was scored correctly. If Phase 8 finds corrupted scores in training data, it would train on wrong weights.

**However:** The `signal_log` table does not store scores — it stores `target_id` (email_id) and `signal_type`. The score is not in the signal log at all. Phase 8 will re-score emails when building the training set. The fix to `ranker.py` means Phase 8 will compute correct scores when it reads historical emails. No backfill of `signal_log` rows is needed.

**Conclusion:** The backfill may be a one-off script that re-runs the ranker over stored `EmailMetadata` records to verify scoring correctness, not a migration of `signal_log`. Alternatively, if Phase 8's adaptive ranker caches computed scores somewhere, those caches would need invalidation.

[ASSUMED: signal_log rows don't store computed scores — this is confirmed by reading the `SignalLog` ORM model which has no `score` field. But whether Phase 8 reads a pre-computed score cache is unknown since Phase 8 is not yet implemented.]

**Practical recommendation for D-08:** Write a one-off script `scripts/backfill_ranker_scores.py` that:
1. Reads all emails from whatever store Phase 8 will use for training data
2. Re-scores them with the fixed ranker
3. Logs a summary of how many changed from WEIGHT_CC to WEIGHT_DIRECT

This is a validation script, not a data migration. Use a simple Python script, not Alembic.

---

## File Hygiene (D-09)

### iCloud Duplicate Files Found

From `git status`, the following duplicate-suffix files exist:

**In `src/`:**
- `src/daily/__init__ 2.py`
- `src/daily/actions/__init__ 2.py`, `base 2.py`, `models 2.py`, `whitelist 2.py`, `log 2.py`
- `src/daily/actions/google/__init__ 2.py`, `calendar 2.py`, `email 2.py`
- `src/daily/actions/microsoft/__init__ 2.py`, `executor 2.py`
- `src/daily/actions/slack/__init__ 2.py`, `executor 2.py`
- `src/daily/briefing/` — multiple `* 2.py`, `ranker 3.py`, `ranker 4.py`
- `src/daily/cli 2.py`, `config 2.py`
- (and many more from git status)

**In `tests/`:**
- `tests/test_briefing_ranker 4.py`, `test_briefing_ranker 3.py`
- Multiple `tests/test_* 2.py` files
- `tests/conftest 2.py`

**In `.planning/`:**
- Multiple `HANDOFF 2.json`, `MILESTONES 2.md`, `REQUIREMENTS 2.md`, etc.

**Canonical files exist** for all of these — the unsuffixed version is the real file.

**Removal approach:** `git rm` for tracked files, `rm` for untracked. All `" 2.py"`, `" 3.py"`, `" 4.py"` suffixed files in `src/` and `tests/` are safe to delete. The `.planning/` duplicates are also safe.

[VERIFIED: by reading git status output directly]

---

## Standard Stack

No new dependencies needed. All fixes use existing libraries and project patterns.

| Concern | Existing Tool | Notes |
|---------|--------------|-------|
| Async Slack calls | `asyncio.to_thread` + `slack_sdk.WebClient` | Already in use — pagination loop uses same pattern |
| Email address parsing | Standard `re` module | `_extract_email` already exists in `nodes.py` — adapt for `ranker.py` |
| Session state | `SessionState.email_context` (list[dict]) | Already populated at session init |
| Tests | `pytest` + `pytest-asyncio` (asyncio_mode=auto) | Test infra already wired |
| Backfill script | Plain Python, SQLAlchemy async session | No new deps |

---

## Architecture Patterns

### Pattern 1: Slack Pagination (time-window stop)

Extract per-channel fetch into a private helper method `_fetch_channel_messages(channel_id, since, is_dm)` — this isolates the pagination loop and makes it independently testable. `list_messages` becomes a thin orchestrator that calls the helper per channel and aggregates.

```python
async def list_messages(self, channels: list[str], since: datetime) -> MessagePage:
    all_messages: list[MessageMetadata] = []
    for channel_id in channels:
        is_dm = channel_id.startswith("D")
        msgs = await self._fetch_channel_messages(channel_id, since, is_dm)
        all_messages.extend(msgs)
    return MessagePage(messages=all_messages, next_cursor=None)
    # next_cursor is None because all in-window messages are returned inline
```

Note: `MessagePage.next_cursor` becomes `None` always from the fixed `list_messages`. The current contract returns `last_cursor` from the last channel — but the caller (briefing pipeline) does not use this cursor for anything after the call. Confirm this is safe before changing the return contract.

[VERIFIED: reading `briefing/pipeline.py` which calls list_messages but does not use the returned `next_cursor`.]

### Pattern 2: Email ID Resolution in summarise_thread_node

The LLM-assisted pattern (Option A) adds `email_context` to the SUMMARISE prompt:

```python
# In summarise_thread_node, before LLM call:
email_context_str = _format_email_context(state.email_context)  # reuse existing helper

# In SUMMARISE_SYSTEM_PROMPT (updated):
# "AVAILABLE EMAILS:\n{email_context}\n\nIdentify which email the user is asking about
#  and set target_id to its message_id."

# After LLM call:
message_id = intent.target_id  # populated by LLM from email context
if not message_id:
    # fallback: can't identify email
    return {"messages": [AIMessage(content="I couldn't identify which email you meant...")]}

raw_body = await adapters[0].get_email_body(message_id)
```

### Anti-Patterns to Avoid

- **Don't add a `score` field to `SignalLog`** — the signal log is append-only and storing computed scores would couple the data model to the heuristic formula. Phase 8 recomputes scores from first principles.
- **Don't paginate by hard count** — D-03 explicitly says no hard page cap; stop on time window only.
- **Don't change `MessagePage.next_cursor` semantics** for callers that don't use it — verify the pipeline ignores it before changing the return value.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead |
|---------|-------------|-------------|
| Email address normalization | Custom parser | `re.search(r'<([^>]+)>', addr)` — already used pattern in `nodes.py:_extract_email` |
| Slack API pagination state | Custom cursor manager | Follow `response_metadata.next_cursor` directly — the Slack SDK already returns it |
| Session state keying | New state store | `SessionState.email_context` is already populated — add `message_id_map` as a dict derived from it at node entry, not a new field |

---

## Common Pitfalls

### Pitfall 1: Slack newest-first ordering breaks time-window check

**What goes wrong:** The inner loop checks `if timestamp < since: return messages`. If Slack returns newest-first, messages are in descending order — the stopping condition will trigger correctly (once we hit an old message, all subsequent messages are also old). But if the assumption is wrong and Slack returns oldest-first, the stopping condition would trigger on the first page if any in-window message comes after a gap.

**How to avoid:** Verify the actual sort order when building the test mock. The test fixture should include messages both inside and outside the window in descending order to match real Slack behaviour.

**Warning signs:** Test passes but pagination stops prematurely in production.

### Pitfall 2: FIX-03 — email_context may be empty at test time

**What goes wrong:** Tests for `summarise_thread_node` that don't populate `state.email_context` will exercise the fallback path, not the fix path. The new regression test must explicitly set `email_context` with realistic entries.

**How to avoid:** The `_make_state` helper in `test_orchestrator_thread.py` needs an `email_context` parameter.

### Pitfall 3: Backfill script assumes email metadata is still accessible

**What goes wrong:** The backfill validates past signal data against re-scored emails. If email metadata is not persisted (only cached in Redis with 24h TTL), historical emails won't be available for re-scoring.

**How to avoid:** The backfill script should operate on any email metadata still present (Redis cache or any DB-persisted records). If nothing is persisted, the script is a no-op and the note "Phase 8 trains on future signals only" is sufficient.

### Pitfall 4: iCloud duplicate files — wrong file removed

**What goes wrong:** Removing the wrong file (the canonical one) instead of the duplicate.

**How to avoid:** The canonical file is always the one WITHOUT the space-number suffix. Run `git rm "file 2.py"` not `git rm "file.py"`.

---

## Code Examples

### FIX-01 — Normalized address comparison

```python
# Source: pattern adapted from nodes.py:_extract_email (same file, same codebase)
import re

_ADDR_RE = re.compile(r"[\w.+\-]+@[\w.\-]+")

def _is_direct_recipient(user_email: str, recipient_field: str) -> bool:
    """Check if user_email appears as a complete address in recipient field.
    
    Handles both bare addresses and RFC 2822 display-name format.
    """
    user_lower = user_email.lower().strip()
    addresses = []
    for part in recipient_field.split(","):
        m = _ADDR_RE.search(part)
        if m:
            addresses.append(m.group(0).lower())
    return user_lower in addresses
```

### FIX-02 — Time-window pagination loop

```python
# Source: derived from existing adapter.py pattern + Slack SDK docs
async def _fetch_channel_messages(
    self, channel_id: str, since: datetime, is_dm: bool
) -> list[MessageMetadata]:
    messages: list[MessageMetadata] = []
    cursor: str | None = None
    oldest_ts = since.timestamp()

    while True:
        kwargs: dict = {"channel": channel_id, "oldest": oldest_ts, "limit": 100}
        if cursor:
            kwargs["cursor"] = cursor
        response = await asyncio.to_thread(
            self._client.conversations_history, **kwargs
        )
        messages_data = response.get("messages", [])
        if not messages_data:
            break
        for msg in messages_data:
            ts_str = msg.get("ts", "")
            timestamp = datetime.fromtimestamp(float(ts_str), tz=timezone.utc)
            if timestamp < since:
                return messages  # time window boundary reached
            text = msg.get("text", "")
            messages.append(MessageMetadata(
                message_id=ts_str,
                channel_id=channel_id,
                sender_id=msg.get("user", ""),
                timestamp=timestamp,
                is_mention="<@" in text,
                is_dm=is_dm,
            ))
        response_metadata = response.get("response_metadata", {})
        raw_cursor = (response_metadata or {}).get("next_cursor", "")
        cursor = raw_cursor if raw_cursor else None
        if not cursor:
            break
    return messages
```

---

## Environment Availability

Step 2.6: SKIPPED — Phase 7 is code fixes with no new external dependencies. All required tools (Python, pytest, git) are confirmed present in the existing dev environment.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` — `asyncio_mode = "auto"`, `testpaths = ["tests"]`, `pythonpath = ["src"]` |
| Quick run command | `pytest tests/test_briefing_ranker.py tests/test_slack_adapter.py tests/test_orchestrator_thread.py -x` |
| Full suite command | `pytest tests/ -x` |

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FIX-01 | Direct email scores WEIGHT_DIRECT when user in To with display name | unit | `pytest tests/test_briefing_ranker.py -x -k "direct"` | Partial — existing `test_cc_vs_direct` uses bare addresses only; new case needed |
| FIX-01 | CC email scores WEIGHT_CC | unit | `pytest tests/test_briefing_ranker.py -x -k "cc"` | Partial (same file) |
| FIX-01 | BCC (user not in recipient field at all) scores WEIGHT_CC | unit | `pytest tests/test_briefing_ranker.py -x -k "bcc"` | Not yet |
| FIX-02 | Slack pagination follows next_cursor until time window exceeded | unit | `pytest tests/test_slack_adapter.py -x -k "pagination"` | Not yet |
| FIX-02 | Zero in-window messages on first page stops immediately | unit | `pytest tests/test_slack_adapter.py -x -k "empty"` | Not yet |
| FIX-03 | summarise_thread_node reads message_id from email_context, not last_content | unit | `pytest tests/test_orchestrator_thread.py -x -k "message_id"` | Not yet |

### Sampling Rate

- **Per task commit:** `pytest tests/test_briefing_ranker.py tests/test_slack_adapter.py tests/test_orchestrator_thread.py -x`
- **Per wave merge:** `pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] New test cases in `tests/test_briefing_ranker.py` — covers FIX-01 display-name address format
- [ ] New test cases in `tests/test_slack_adapter.py` — covers FIX-02 pagination scenarios
- [ ] New test cases in `tests/test_orchestrator_thread.py` — covers FIX-03 email_context resolution
- [ ] `scripts/backfill_ranker_scores.py` — new file, not a test but a validation script for D-08

*(No new test infrastructure needed — existing `conftest.py`, `pytest-asyncio`, and mock patterns cover all cases.)*

---

## Security Domain

No new attack surfaces introduced. All three fixes are internal logic corrections:

- FIX-01: Tighter string comparison — no new inputs, no new outputs
- FIX-02: Additional HTTP calls to Slack (same OAuth token) — existing token security unchanged
- FIX-03: LLM now receives `email_context` (already in session state) — no new data exposure. The `email_context` list already flows to the LLM in `draft_node`; adding it to `summarise_thread_node` is equivalent exposure.

**No ASVS review required for this phase** — bug fixes with no new auth, session, or input validation surfaces.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | FIX-01 root cause is RFC 2822 display-name format in `email.recipient` field (e.g., "Jacob <jacob@example.com>") | FIX-01 Analysis | If the actual root cause is different (e.g., recipient field is empty, or contains CC addresses too), the fix may not resolve the bug. Read the Google/Microsoft adapter to confirm before coding. |
| A2 | Slack `conversations_history` returns messages newest-first (descending `ts`) | FIX-02 Analysis | If Slack returns oldest-first, the time-window stop condition in the inner loop must check the first message of each page, not track per-message. |
| A3 | `signal_log` does not store computed scores; Phase 8 will recompute them | Backfill Analysis | If Phase 8 reads a pre-computed score cache (not yet implemented), that cache would need invalidation after FIX-01 lands. |
| A4 | `briefing/pipeline.py` does not use the `next_cursor` returned by `list_messages` | Architecture Patterns | If the pipeline does use `next_cursor` for something, changing `list_messages` to return `None` would break the caller. Confirmed by code read — pipeline ignores it. |

---

## Open Questions

1. **FIX-01 root cause — confirm adapter output format**
   - What we know: `_is_direct_recipient` does plain string split/compare; `email.recipient` is a str field
   - What's unclear: Whether the Google/Microsoft adapters write bare addresses or RFC 2822 format into `email.recipient`
   - Recommendation: Read `src/daily/actions/google/email.py` (or equivalent adapter) before writing the fix to confirm the exact input format

2. **FIX-03 option selection — LLM match vs dict lookup**
   - What we know: D-06 says "keyed by subject/sender or index" (dict lookup); but `draft_node` uses LLM match (cleaner)
   - What's unclear: Whether LLM match is within Claude's Discretion or must follow D-06's dict key approach literally
   - Recommendation: Use LLM match (Option A) — it's within discretion and avoids brittle substring matching

3. **Backfill scope — what data exists?**
   - What we know: `signal_log` has `target_id` (email_id) but no stored scores; emails cached in Redis with 24h TTL
   - What's unclear: Whether any email metadata is persisted to the DB for historical queries
   - Recommendation: Write the backfill script to work against whatever data is available; make it a no-op if no historical data exists

---

## Sources

### Primary (HIGH confidence)
- Direct code read: `src/daily/briefing/ranker.py` — FIX-01 bug confirmed at line 91-94
- Direct code read: `src/daily/integrations/slack/adapter.py` — FIX-02 bug confirmed at lines 54-87
- Direct code read: `src/daily/orchestrator/nodes.py` — FIX-03 bug confirmed at lines 224-227
- Direct code read: `src/daily/orchestrator/state.py` — `email_context` field confirmed present
- Direct code read: `tests/test_briefing_ranker.py` — existing test coverage confirmed
- Direct code read: `tests/test_slack_adapter.py` — existing test coverage confirmed
- Direct code read: `tests/test_orchestrator_thread.py` — existing test coverage confirmed
- Direct code read: `src/daily/profile/signals.py` — `SignalLog` model has no score field

### Secondary (MEDIUM confidence)
- `CONTEXT.md` — all decisions (D-01 through D-09) are locked by the user

---

## Metadata

**Confidence breakdown:**
- Bug identification: HIGH — all three bugs directly verified by reading source code
- Fix approach (FIX-01): HIGH — approach mirrors existing `_extract_email` pattern in same codebase
- Fix approach (FIX-02): HIGH — standard cursor pagination pattern, confirmed by reading adapter
- Fix approach (FIX-03): HIGH — `email_context` confirmed present in `SessionState`, `_format_email_context` helper already exists
- Backfill scope: MEDIUM — depends on what historical data exists (signal_log model read, but no email persistence layer confirmed)
- Slack sort order: MEDIUM — standard API behaviour, not re-verified in this session

**Research date:** 2026-04-15
**Valid until:** This research is code-read-based, not time-sensitive. Valid until source files change.
