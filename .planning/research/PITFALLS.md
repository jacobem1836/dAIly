# Domain Pitfalls: Adding Intelligence/Memory/Autonomy to an Existing AI Assistant

**Domain:** Retrofitting learning, memory, and autonomy into a production LangGraph + FastAPI backend
**Researched:** 2026-04-15
**Scope:** Integration-specific pitfalls — not greenfield design mistakes

---

## Critical Pitfalls

Mistakes that cause rewrites, data loss, or broken security invariants.

---

### Pitfall 1: Corrupting Existing LangGraph Checkpoints When Adding State Fields

**What goes wrong:** You add new fields to `SessionState` (e.g. `memory_context`, `autonomy_level`,
`conversation_mode`) and redeploy. Active sessions that were interrupted mid-graph — waiting on
the `approval_node` interrupt — load their checkpoint and encounter a state dict that no longer
matches the schema. Missing required fields or type-incompatible values cause silent deserialization
failures or crashes at graph resume.

**Why it happens:** `AsyncPostgresSaver` serialises the full `SessionState` snapshot at every step.
When you widen the schema, old snapshots don't have the new keys. LangGraph provides forwards
compatibility for *adding* keys (missing keys default), but *renaming or removing* keys loses saved
state. Type changes on existing keys can cause pydantic validation failures on checkpoint reload.

**Consequence:** Any in-flight session (interrupted at `approval_node`) becomes unresumable. In the
worst case the graph raises on startup when it tries to reload the last checkpoint.

**Prevention:**
- Only add new fields with `Field(default=...)` — never rename or remove existing `SessionState` fields
- Treat `SessionState` keys as append-only for the duration of a session's lifetime
- Before any release that touches `SessionState`, clear or expire active checkpoints in dev; test
  resume of a pre-existing interrupted thread in staging
- Keep a copy of the old state schema and write a migration test that deserialises an old snapshot

**Detection:** Watch for `ValidationError` at checkpoint load; test `graph.aget_state(config)` on a
checkpoint created with the previous schema before deploying.

**Confidence:** HIGH (confirmed in LangGraph GitHub issues #6104, #6623, #5862)

---

### Pitfall 2: Mem0 Memory Extraction Producing Junk at Scale

**What goes wrong:** You wire mem0 into the LangGraph nodes to extract user facts after each session.
Over days, the extraction LLM fabricates demographics, invents categories ("software developer at Google",
"formal communication style"), re-extracts recalled memories as new facts (feedback loop), and stores
system internals (tool configs, file paths, IP addresses) as "user memories." In a real production audit
of a comparable system, 97.8% of 10,134 entries were identified as junk after 32 days.

**Why it happens:** The mem0 extraction pipeline has no signal-quality filter. Every message — including
the LLM's own recalled memories injected back into context — is treated as new user-stated fact.
The feedback loop: recall → inject into prompt → extract recalled content as new memory → store → repeat.

**Consequence:** The user profile fills with noise. When this noise is injected into the briefing prompt
("User is a software developer at Google") it degrades output quality and introduces false personalisation.
The memory transparency UI (MEM-01/MEM-02) becomes unusable because the user sees hundreds of invented
facts they never stated.

**Prevention:**
- Do NOT use mem0's default auto-extraction on all messages. Trigger extraction only on explicit
  high-confidence signal events (correction, re_request, expand from `SignalType`) — these already
  exist in the `signal_log` table
- Apply a confidence threshold: only store extractions where the extraction LLM rates confidence > 0.8
- Mark injected memory context clearly (e.g. prefix `[RECALLED MEMORY]`) so the extraction pass can
  filter it out
- Cap memory entries per category (e.g. max 20 per user) and run a deduplication/consolidation pass
- For v1.1 scope: consider building a lighter custom extraction rather than delegating entirely to mem0

**Detection:** Set up a daily count of new memory entries per user; alert if > 20 new entries/day (likely
a feedback loop). Manually audit 10 random entries per week for the first month.

**Confidence:** HIGH (direct production audit reported in mem0 GitHub issue #4573)

---

### Pitfall 3: Breaking the Approval Gate When Adding Autonomy Levels

**What goes wrong:** You add a trusted-actions autonomy level (`suggest` / `approve` / `auto`).
The implementation conditionally skips `approval_node`'s `interrupt()` call. But the conditional logic
lives in the node function rather than in the graph's routing edges. When `interrupt()` is skipped,
LangGraph still writes a checkpoint for `approval_node` — but the graph proceeds to `execute_node`
without the `approval_decision` field being set. `execute_node` reads `approval_decision` which is
`None`, and either crashes or silently auto-approves.

**Why it happens:** The v1.0 approval flow assumes `interrupt()` always fires in `approval_node`. Adding
a conditional bypass inside the node function rather than via a conditional edge means the graph
topology doesn't reflect the new flow. `execute_node` has no way to distinguish "user approved" from
"approval was skipped."

**Consequence:** High-impact actions (send email, create calendar event) execute without user confirmation
when the conditional has a bug. This is the most security-critical regression in this feature list.
ACT-04 and SEC-05 are both violated.

**Prevention:**
- Model autonomy levels as a graph-topology change, not a conditional inside `approval_node`:
  - Add an `autonomy_router` conditional edge *before* `approval_node`
  - Route `auto` level directly to `execute_node`, bypassing `approval_node` entirely
  - Route `approve` and `suggest` through `approval_node` as today
- `execute_node` must check `state.approval_decision is not None OR state.autonomy_level == "auto"`;
  reject execution if neither condition holds — this is the safety invariant
- Write an integration test that: sets autonomy to `auto`, triggers a high-impact action, asserts
  it executes; then resets to `approve`, triggers same action, asserts it hits the interrupt gate
- Restrict `auto` level to a whitelist of low-impact action types initially (e.g. only read/summarise,
  not send/create)

**Detection:** Add an assertion at the start of `execute_node`: if `approval_decision is None` and
`autonomy_level != "auto"`, raise `RuntimeError("execute_node reached without approval — invariant violation")`.

**Confidence:** HIGH (based on LangGraph interrupt/Command patterns and direct code analysis of v1.0 nodes.py)

---

### Pitfall 4: Thread ID / User ID Conflation in Cross-Session Memory

**What goes wrong:** When wiring cross-session memory (INTEL-02), you use `thread_id` as the memory
namespace key. In LangGraph, `thread_id` scopes a *conversation session* — one session = one `thread_id`.
A single user will accumulate dozens of thread IDs over weeks. Memories stored under `thread_id` are
session-scoped, not user-scoped, so cross-session retrieval finds nothing.

**Why it happens:** LangGraph's `AsyncPostgresSaver` config requires a `thread_id`. This same
`thread_id` is easy to reuse as the memory lookup key because it is already in the graph config.
But the memory layer needs a stable identity (`user_id`) that survives across all sessions.

**Consequence:** Every new session has zero memory context — the adaptive personalisation never
actually adapts. The feature ships but has no observable effect. Days pass before the bug is noticed
because the system falls back to heuristics silently.

**Prevention:**
- Always scope memory operations with `user_id` (the stable identity), not `thread_id`
- The graph config carries both: `{"configurable": {"thread_id": ..., "user_id": ...}}`
- `user_id` is already in `SessionState.active_user_id` — use this for all memory read/write calls
- Write a test: create two sessions for the same user (different thread IDs), store a memory in
  session 1, assert it is retrievable in session 2

**Confidence:** HIGH (confirmed in LangGraph memory migration docs and community patterns)

---

## Moderate Pitfalls

Mistakes that degrade feature quality or create significant tech debt.

---

### Pitfall 5: Signal-to-Score Feedback Loop Locking In Bad Preferences

**What goes wrong:** The adaptive prioritisation feature (INTEL-01) trains a learned scorer on
`signal_log` data. Early signals are noisy — the user skips things they would normally care about
(skipped because busy, not unimportant). The scorer learns these skips as "low priority" and stops
surfacing that content. Future skips on that content reinforce the score further. The user never
sees it, so they never correct it.

**Why it happens:** Implicit signals (skip, follow_up) are proxies for preference, not statements
of preference. A skip on a given morning can mean "I already knew this" or "I'm in a hurry" — the
system cannot distinguish between these without additional context. Optimising directly on engagement
signals introduces causality problems: low rank → fewer exposures → fewer engagement signals →
confirmed low rank.

**Consequence:** High-priority content that the user happened to skip in early sessions gets
permanently suppressed. The user never sees the divergence because the heuristic fallback is gone.

**Prevention:**
- Keep the heuristic scorer as a floor, not a fallback. Blend: `final_score = α * learned_score + (1-α) * heuristic_score`
  with α starting at 0.2 and increasing only as signal volume grows (> 30 days of data)
- Apply an exploration budget: randomly surface 10–15% of content at heuristic rank regardless
  of learned score (prevents reinforcing suppression of unseen content)
- Signal weights should decay by recency — a skip 3 weeks ago should count less than a skip today
- Preserve the `signal_log` append-only invariant (already established in v1.0); never update
  signal rows — only add new signals that override old ones

**Detection:** Monthly audit: compute the distribution of learned scores for high-heuristic-score
items (important sender, deadline keyword). If these consistently rank low in the learned scorer,
the feedback loop is active.

**Confidence:** MEDIUM (established pattern in recommender systems literature; adapted for this context)

---

### Pitfall 6: Memory Deletion Leaving Orphaned Embeddings (MEM-02)

**What goes wrong:** The user requests to delete a specific memory (MEM-02). The implementation
deletes the row from the memories table. But the pgvector embedding stored as a separate vector
row (or via an ORM relationship) is not deleted. Subsequent similarity searches still retrieve
the embedding, reconstruct the deleted memory's context, and surface it in briefings — effectively
undeleting it.

**Why it happens:** pgvector stores embeddings as rows in a table with a foreign key to the
source record. If the deletion only removes the source record without cascading to the vector
row (or if the ORM relationship doesn't declare `CASCADE DELETE`), the vector row becomes an
orphan that participates in similarity search.

**Consequence:** The user is told their memory was deleted. It resurfaces in future briefings.
This is a correctness violation (MEM-02) and a trust failure — the user believed they had
control over their data.

**Prevention:**
- Model the memory table with `ON DELETE CASCADE` on the embedding FK from the start
- Deletion endpoint must delete both the source row and the vector row in a single transaction
- Write a test: insert a memory with its embedding, delete it, run a similarity search that
  would have matched it, assert the result set is empty

**Confidence:** MEDIUM (confirmed by pgvector + langchain delete issue discussion; adapted)

---

### Pitfall 7: Adaptive Tone Polluting the Briefing System Prompt (CONV-03)

**What goes wrong:** Adaptive tone (CONV-03) adjusts verbosity and formality based on context
signals. The implementation appends tone guidance to the system prompt each turn: "User prefers
casual tone today, verbosity level 2 of 5." Over a long session, accumulated tone directives
grow the prompt. Combined with the briefing narrative already in `RESPOND_SYSTEM_PROMPT`, the
context window fills faster than expected — causing truncation of the briefing narrative or
the email context injected later.

**Why it happens:** `RESPOND_SYSTEM_PROMPT` already injects `briefing_narrative` and `email_context`.
Adding adaptive tone as another injected string layer increases prompt size without bound. The
voice loop target is sub-500ms for follow-ups; prompt inflation delays first-token time.

**Prevention:**
- Encode adaptive tone as structured fields in the existing `UserPreferences` model (already stored
  in `SessionState.preferences`) rather than as natural-language prompt additions
- The system prompt reads the structured field: `tone={preferences.tone}` (already present in v1.0
  in `RESPOND_SYSTEM_PROMPT`)
- Contextual tone shifts (less formal mid-session) should update `SessionState.preferences.tone`
  in-place rather than appending narrative instructions
- Set a hard prompt size budget and assert it in tests: total system prompt + briefing narrative
  must fit within 8K tokens

**Confidence:** MEDIUM (latency + context window concern; specific to this stack and existing prompt structure)

---

### Pitfall 8: Scheduler User Email Bug (FIX-01) Corrupting Adaptive Prioritisation Training Data

**What goes wrong:** FIX-01 (`user_email=""` in scheduler) means that during every scheduled
briefing run, `WEIGHT_DIRECT` never fires — emails addressed directly to the user are scored
as `WEIGHT_CC` (2pts instead of 10pts). If this bug is not fixed *before* INTEL-01 (adaptive
prioritisation) is trained, the signal data used to train the learned scorer will be based on
incorrect heuristic scores. The learned scorer will learn wrong baseline weights.

**Why it happens:** The signal_log records which items were surfaced and at what rank. If the
rank is systematically wrong (due to FIX-01), the training labels are corrupted. Fixing FIX-01
later does not retroactively correct the training data.

**Consequence:** The adaptive scorer trains on poisoned labels. High-importance direct emails
are treated as medium-weight items. The learning makes the bad heuristic permanent.

**Prevention:** Fix FIX-01 (and FIX-02, FIX-03) *before* implementing INTEL-01. Do not collect
training signal while known bugs in the ranker are active. This is a hard sequencing dependency.

**Detection:** Before training, sanity-check signal_log: verify that WEIGHT_DIRECT signals exist
in historical data (they will not if FIX-01 was active during data collection).

**Confidence:** HIGH (direct code analysis of existing v1.0 system; PROJECT.md confirms FIX-01 is known)

---

### Pitfall 9: Memory Transparency Exposing Inferred vs Stated Facts Without Attribution (MEM-01)

**What goes wrong:** MEM-01 ("What do you know about me?") returns a list of memory entries.
Some entries were directly stated by the user ("I don't like lengthy emails"). Others were
inferred by the extraction LLM from conversation fragments ("User appears to work in finance").
The UI presents both with equal authority. The user sees an invented inference and loses trust
in the memory system entirely.

**Why it happens:** The memory store has no provenance field — it doesn't record whether a
memory was directly stated, inferred, or derived from a signal event. Without provenance, the
transparency response cannot distinguish categories.

**Prevention:**
- Add a `source` field to every memory entry at creation time: `"stated"`, `"inferred"`, `"signal"` (from signal_log)
- MEM-01 response must include source attribution: "You told me..." vs "I inferred from our
  conversations that..."
- Inferred memories should have lower display priority and an explicit uncertainty label
- MEM-02 (edit/delete) is more critical for inferred memories — surface an easy delete path

**Confidence:** MEDIUM (UX trust pattern; based on first-principles reasoning and AI memory design literature)

---

## Minor Pitfalls

---

### Pitfall 10: APScheduler In-Process Blocking on Memory Extraction During Briefing Precompute

**What goes wrong:** The briefing precompute job (APScheduler, 05:30 cron) is extended to also
run memory extraction/consolidation as part of the overnight pipeline. Memory extraction makes
additional LLM calls (embedding generation, extraction). If these block the asyncio event loop
or run synchronously, the briefing precompute time increases.

**Prevention:** All memory extraction tasks must be `async` and awaited within the APScheduler
asyncio job. Never call mem0 or pgvector operations synchronously from an async context.
Instrument the briefing pipeline end-to-end with timing logs. Run extraction as a separate
scheduled job, not chained to the briefing precompute.

---

### Pitfall 11: Autonomy Level Not in UserPreferences Causing KeyError in Node Code

**What goes wrong:** The user sets their autonomy level (ACT-07). It is stored in `UserPreferences`
(loaded into `SessionState.preferences` at session start). Mid-session, a node checks
`state.preferences["autonomy_level"]` but `UserPreferences` does not have this field in v1.0 —
it will return `KeyError` or Pydantic validation error.

**Prevention:** Extend `UserPreferences` with `autonomy_level: Literal["suggest", "approve", "auto"] = "approve"`
before writing any node code that reads it. The default `"approve"` preserves the v1.0 behaviour
exactly for all existing sessions. The JSONB-backed `UserProfile` model already supports schema
evolution without migrations (per D-04).

---

### Pitfall 12: pgvector Similarity Search Without User ID Filter Returning Cross-User Memories

**What goes wrong:** This is a single-user system today — but the schema has a `user_id` FK.
If memory search queries do not include a `WHERE user_id = :user_id` filter, all memories in
the table participate in similarity search.

**Prevention:** All pgvector search calls must include `user_id` as a metadata filter. Write a
test with two users' memories in the table; assert that searching as user A never returns user B's entries.
Even in a single-user system, establish this constraint now before v2.0 multi-user scenarios.

---

## Phase-Specific Warnings

| Phase | Feature | Likely Pitfall | Mitigation |
|-------|---------|---------------|------------|
| Fix bugs first | FIX-01/02/03 | Training data poisoned if adaptive ranker built before FIX-01 | Fix all three bugs before starting INTEL-01 |
| INTEL-01 | Adaptive prioritisation | Feedback loop locking in bad preferences (Pitfall 5) | Blend heuristic floor + exploration budget |
| INTEL-01 | Signal-based learning | Sparse signals in first 30 days make learned scores noisy | Use α-blending; don't remove heuristics |
| INTEL-02 | Cross-session memory | Thread ID / user ID conflation (Pitfall 4) | Verify user_id scoping in first test |
| INTEL-02 | mem0 extraction | Hallucinated memories, feedback loop (Pitfall 2) | Signal-triggered extraction only; confidence filter |
| MEM-01/02/03 | Memory transparency | Orphaned embeddings after delete (Pitfall 6) | CASCADE DELETE; transactional delete test |
| MEM-01/02/03 | Memory display | Inferred vs stated conflation (Pitfall 9) | Add `source` field to memory entries at creation |
| ACT-07 | Trusted actions | Broken approval gate on conditional bypass (Pitfall 3) | Model as graph topology change, not in-node conditional |
| ACT-07 | Autonomy level field | Missing field in UserPreferences (Pitfall 11) | Extend UserPreferences before any node code reads it |
| CONV-01/02/03 | Conversational flow | State schema changes breaking active checkpoints (Pitfall 1) | Append-only state fields with defaults |
| CONV-03 | Adaptive tone | System prompt bloat from narrative tone injections (Pitfall 7) | Structured fields, not narrative injections |
| All intelligence phases | Memory extraction | Sensitive data (IP, tool configs) stored as memories (Pitfall 2) | Explicit exclude-list filter; signal-triggered extraction only |

---

## Sources

- LangGraph GitHub issues #6104, #6623, #5862 — checkpoint schema and thread ID bugs (HIGH)
- LangGraph docs — [State schema migration compatibility](https://docs.langchain.com/oss/javascript/langgraph/graph-api) (HIGH)
- LangGraph docs — [How to migrate to LangGraph memory](https://python.langchain.com/docs/versions/migrating_memory/) (HIGH)
- LangGraph forum — [How to update graph state while preserving interrupts](https://forum.langchain.com/t/how-to-update-graph-state-while-preserving-interrupts/1655) (HIGH)
- mem0 GitHub issue #4573 — [97.8% junk in production audit](https://github.com/mem0ai/mem0/issues/4573) (HIGH)
- mem0 docs — [pgvector configuration](https://docs.mem0.ai/components/vectordbs/dbs/pgvector) (HIGH)
- LangChain GitHub issue #9312 — [pgvector delete not implemented](https://github.com/langchain-ai/langchain/issues/9312) (MEDIUM)
- Cloud Security Alliance — [Autonomy Levels for Agentic AI](https://cloudsecurityalliance.org/blog/2026/01/28/levels-of-autonomy) (MEDIUM)
- DigitalOcean — [LangGraph + Mem0 integration](https://www.digitalocean.com/community/tutorials/langgraph-mem0-integration-long-term-ai-memory) (MEDIUM)
- FutureSmart — [mem0 + LangGraph integration patterns](https://blog.futuresmart.ai/ai-agents-memory-mem0-langgraph-agent-integration) (MEDIUM)
- Recommender systems literature — cold start, feedback loops, exploration budgets (MEDIUM)
- dAIly v1.0 codebase — direct analysis of `orchestrator/state.py`, `orchestrator/nodes.py`, `profile/signals.py` (HIGH)
