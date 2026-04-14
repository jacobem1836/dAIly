---
phase: 03-orchestrator
plan: 01b
type: execute
wave: 2
depends_on: ["03-01"]
files_modified:
  - src/daily/profile/signals.py
  - src/daily/orchestrator/__init__.py
  - src/daily/orchestrator/state.py
  - src/daily/orchestrator/models.py
  - alembic/versions/003_add_user_profile_signal_log.py
  - tests/test_signal_log.py
autonomous: true
requirements:
  - PERS-02

must_haves:
  truths:
    - "signal_log table exists with append-only schema"
    - "SignalType enum contains skip, correction, re_request, follow_up, expand"
    - "Signal service can append signals"
    - "OrchestratorIntent validates action is one of answer, summarise_thread, skip, clarify"
    - "SessionState has messages, briefing_narrative, active_user_id, preferences fields"
  artifacts:
    - path: "src/daily/profile/signals.py"
      provides: "SignalLog ORM + SignalType enum + append_signal()"
      contains: "class SignalLog"
    - path: "src/daily/orchestrator/state.py"
      provides: "SessionState Pydantic model for LangGraph"
      contains: "class SessionState"
    - path: "src/daily/orchestrator/models.py"
      provides: "OrchestratorIntent response model (SEC-05)"
      contains: "class OrchestratorIntent"
  key_links:
    - from: "src/daily/profile/signals.py"
      to: "src/daily/db/models.py"
      via: "imports Base from db.models"
      pattern: "from daily.db.models import Base"
    - from: "alembic/versions/003_add_user_profile_signal_log.py"
      to: "src/daily/profile/models.py"
      via: "migration includes user_profile table from Plan 01"
      pattern: "user_profile"
---

<objective>
Create the signal log data layer, orchestrator state/intent models, and the Alembic migration for both user_profile and signal_log tables.

Purpose: Completes the data layer for interaction signal capture (PERS-02) and defines the orchestrator's type contracts (SessionState, OrchestratorIntent) that Plan 02 builds on.
Output: `daily.profile.signals` module, `daily.orchestrator` package with state and models, Alembic migration for both new tables.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/phases/03-orchestrator/03-CONTEXT.md
@.planning/phases/03-orchestrator/03-RESEARCH.md
@.planning/phases/03-orchestrator/03-01-SUMMARY.md

<interfaces>
<!-- Contracts from Plan 01 that this plan builds on -->

From src/daily/db/models.py:
```python
class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
```

From src/daily/profile/models.py (created in Plan 01):
```python
class UserProfile(Base):
    __tablename__ = "user_profile"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    preferences: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
```

From src/daily/briefing/models.py:
```python
class BriefingOutput(BaseModel):
    narrative: str
    generated_at: datetime
    version: int = 1
```

From src/daily/integrations/models.py:
```python
class EmailMetadata(BaseModel):
    message_id: str; thread_id: str; subject: str; sender: str; ...
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Create signal_log table, SignalType enum, append_signal service, orchestrator models, and Alembic migration</name>
  <files>
    src/daily/profile/signals.py,
    src/daily/orchestrator/__init__.py,
    src/daily/orchestrator/state.py,
    src/daily/orchestrator/models.py,
    alembic/versions/003_add_user_profile_signal_log.py,
    tests/test_signal_log.py
  </files>
  <read_first>
    - src/daily/db/models.py (Base class, ORM patterns)
    - src/daily/profile/models.py (just created — UserProfile for migration)
    - src/daily/briefing/models.py (BriefingOutput — referenced in SessionState)
    - src/daily/integrations/models.py (EmailMetadata — referenced in SessionState)
    - alembic/versions/ (existing migration naming pattern)
    - alembic/env.py (migration target metadata)
  </read_first>
  <behavior>
    - Test: append_signal(user_id=1, signal_type=SignalType.skip, target_id="msg-123") creates a row in signal_log
    - Test: append_signal with signal_type=SignalType.follow_up works
    - Test: SignalType enum contains exactly: skip, correction, re_request, follow_up, expand
    - Test: OrchestratorIntent validates action must be one of "answer", "summarise_thread", "skip", "clarify"
    - Test: OrchestratorIntent rejects action="execute_code" (arbitrary actions not allowed, SEC-05)
    - Test: SessionState has messages, briefing_narrative, active_user_id, preferences fields
  </behavior>
  <action>
1. Create `src/daily/profile/signals.py`:
   - `class SignalType(str, Enum)` with values: `skip = "skip"`, `correction = "correction"`, `re_request = "re_request"`, `follow_up = "follow_up"`, `expand = "expand"` (per D-07)
   - `class SignalLog(Base)` ORM model:
     - `__tablename__ = "signal_log"`
     - `id: Mapped[int] = mapped_column(primary_key=True)`
     - `user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))`
     - `signal_type: Mapped[str] = mapped_column(String(50))` (stores enum value)
     - `target_id: Mapped[str | None] = mapped_column(String(255), nullable=True)` (email_id, event_id, etc.)
     - `metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)` (flexible extra data)
     - `created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())`
   - `async def append_signal(user_id: int, signal_type: SignalType, session: AsyncSession, target_id: str | None = None, metadata: dict | None = None) -> None`:
     - Create a SignalLog row, add to session, commit. Per D-08: fire-and-forget pattern — callers will wrap in asyncio.create_task().

2. Create `src/daily/orchestrator/__init__.py` (empty).

3. Create `src/daily/orchestrator/state.py`:
   ```python
   from typing import Annotated
   from pydantic import BaseModel, Field
   from langgraph.graph.message import add_messages

   class SessionState(BaseModel):
       messages: Annotated[list, add_messages] = Field(default_factory=list)
       briefing_narrative: str = ""
       active_user_id: int = 0
       preferences: dict = Field(default_factory=dict)
       active_section: str = ""  # current briefing section pointer
   ```
   Per D-09: session state persisted by LangGraph checkpointer. Only summaries, never raw bodies.

4. Create `src/daily/orchestrator/models.py`:
   ```python
   from typing import Literal
   from pydantic import BaseModel

   class OrchestratorIntent(BaseModel):
       action: Literal["answer", "summarise_thread", "skip", "clarify"]
       narrative: str
       target_id: str | None = None
   ```
   Per D-03/SEC-05: LLM output validated against this schema. Only these 4 actions are permitted. No "execute", "send", "call" actions — those belong to Phase 4.

5. Create Alembic migration `alembic/versions/003_add_user_profile_signal_log.py`:
   - Use the same revision ID pattern as existing migrations
   - Run `alembic revision --autogenerate -m "add user_profile and signal_log tables"` to generate, OR write manually with `op.create_table("user_profile", ...)` and `op.create_table("signal_log", ...)`
   - Ensure the `alembic/env.py` target_metadata imports `Base.metadata` which includes the new models (may need to import `daily.profile.models` and `daily.profile.signals` in env.py)

6. Create `tests/test_signal_log.py` with tests per behavior block. Create `tests/test_orchestrator_models.py` (or add to test_signal_log.py) for OrchestratorIntent and SessionState validation tests.
  </action>
  <verify>
    <automated>cd /Users/jacobmarriott/Documents/Personal/dAIly && uv run pytest tests/test_signal_log.py -x -v</automated>
  </verify>
  <acceptance_criteria>
    - src/daily/profile/signals.py contains `class SignalType(str, Enum):`
    - src/daily/profile/signals.py contains `skip = "skip"`
    - src/daily/profile/signals.py contains `expand = "expand"`
    - src/daily/profile/signals.py contains `class SignalLog(Base):`
    - src/daily/profile/signals.py contains `__tablename__ = "signal_log"`
    - src/daily/profile/signals.py contains `async def append_signal(`
    - src/daily/orchestrator/state.py contains `class SessionState(BaseModel):`
    - src/daily/orchestrator/state.py contains `messages: Annotated[list, add_messages]`
    - src/daily/orchestrator/state.py contains `briefing_narrative: str`
    - src/daily/orchestrator/models.py contains `class OrchestratorIntent(BaseModel):`
    - src/daily/orchestrator/models.py contains `action: Literal["answer", "summarise_thread", "skip", "clarify"]`
    - alembic/versions/ contains a migration file with "user_profile" and "signal_log"
    - tests/test_signal_log.py exits 0
  </acceptance_criteria>
  <done>SignalLog ORM model, SignalType enum, append_signal service, SessionState, OrchestratorIntent models all created and tested. Alembic migration generated for both new tables.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Signal metadata -> signal_log | Metadata dict could contain arbitrary data — validate size |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-03-02 | Information Disclosure | signal_log metadata_json | accept | Single-user Phase 3; metadata is system-generated, not user-supplied. No PII risk at this scale. |
| T-03-03 | Spoofing | OrchestratorIntent.action | mitigate | Literal["answer", "summarise_thread", "skip", "clarify"] — LLM cannot inject arbitrary action types; Pydantic rejects unknown values |
</threat_model>

<verification>
1. `uv run pytest tests/test_signal_log.py -x` passes
2. `uv run python -c "from daily.profile.signals import SignalLog, SignalType; from daily.orchestrator.state import SessionState; from daily.orchestrator.models import OrchestratorIntent; print('All imports OK')"` exits 0
3. Alembic migration file exists in alembic/versions/
</verification>

<success_criteria>
- Signal log append tests pass
- OrchestratorIntent rejects invalid action values
- SessionState includes messages with add_messages annotation
- Alembic migration covers both user_profile and signal_log tables
</success_criteria>

<output>
After completion, create `.planning/phases/03-orchestrator/03-01b-SUMMARY.md`
</output>
