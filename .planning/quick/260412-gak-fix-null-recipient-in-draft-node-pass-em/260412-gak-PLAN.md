---
phase: quick-260412-gak
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/daily/orchestrator/state.py
  - src/daily/orchestrator/session.py
  - src/daily/orchestrator/nodes.py
autonomous: true
requirements: []
must_haves:
  truths:
    - "draft_node LLM receives structured email metadata (sender, subject, thread_id, message_id) in its prompt"
    - "LLM output includes thread_id and message_id fields for reply threading"
    - "ActionDraft is populated with recipient, thread_id, and thread_message_id from the matched email"
    - "If no match found in session email_context, draft_node falls back to adapter list_emails()"
  artifacts:
    - path: "src/daily/orchestrator/state.py"
      provides: "email_context field on SessionState"
      contains: "email_context"
    - path: "src/daily/orchestrator/session.py"
      provides: "email_context population during session init"
      contains: "email_context"
    - path: "src/daily/orchestrator/nodes.py"
      provides: "DRAFT_SYSTEM_PROMPT with email_context placeholder, draft_node threading"
      contains: "email_context"
  key_links:
    - from: "src/daily/orchestrator/session.py"
      to: "src/daily/orchestrator/state.py"
      via: "initialize_session_state populates email_context"
      pattern: "email_context"
    - from: "src/daily/orchestrator/nodes.py"
      to: "state.email_context"
      via: "draft_node reads email_context and formats into prompt"
      pattern: "state\\.email_context"
---

<objective>
Fix null recipient in draft_node by passing structured email metadata to the LLM prompt.

Purpose: The LLM currently has no structured email data (sender, subject, thread_id, message_id) when
drafting replies, so it outputs recipient=null. This makes email replies non-functional.

Output: draft_node produces ActionDraft with correct recipient, thread_id, and thread_message_id
populated from matched email metadata.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@src/daily/orchestrator/state.py
@src/daily/orchestrator/session.py
@src/daily/orchestrator/nodes.py
@src/daily/integrations/models.py
@src/daily/briefing/models.py
@src/daily/actions/base.py (lines 57-90)

<interfaces>
<!-- Key types and contracts the executor needs. -->

From src/daily/integrations/models.py:
```python
class EmailMetadata(BaseModel):
    message_id: str
    thread_id: str
    subject: str
    sender: str
    recipient: str
    timestamp: datetime
    is_unread: bool
    labels: list[str]
```

From src/daily/actions/base.py:
```python
class ActionDraft(BaseModel):
    action_type: ActionType
    recipient: str | None = None
    subject: str | None = None
    body: str
    thread_id: str | None = None
    thread_message_id: str | None = None
    # ... (calendar/slack fields omitted)
```

From src/daily/orchestrator/session.py:
```python
def get_email_adapters() -> list:
    """Retrieve registered email adapters."""
    return _email_adapters

async def initialize_session_state(user_id, redis, db_session, session_date=None) -> dict:
    """Load cached briefing and user preferences into initial state."""
    # Currently returns: briefing_narrative, active_user_id, preferences
    # Does NOT populate email metadata yet
```

From src/daily/orchestrator/state.py:
```python
class SessionState(BaseModel):
    messages: Annotated[list, add_messages] = Field(default_factory=list)
    briefing_narrative: str = ""
    active_user_id: int = 0
    preferences: dict = Field(default_factory=dict)
    active_section: str = ""
    pending_action: ActionDraft | None = None
    approval_decision: str | None = None
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add email_context to SessionState and populate during session init</name>
  <files>src/daily/orchestrator/state.py, src/daily/orchestrator/session.py</files>
  <action>
**state.py:** Add a new field to SessionState:
```python
email_context: list[dict] = Field(default_factory=list)
```
Use `list[dict]` (not `list[EmailMetadata]`) because LangGraph state serialisation works cleanly with plain dicts. Each dict has keys: message_id, thread_id, subject, sender, recipient, timestamp (ISO string).

Add the import if needed but prefer keeping it simple with dict.

**session.py:** In `initialize_session_state()`, after loading briefing and preferences, fetch recent email metadata from registered adapters and include it in the returned state dict:

```python
# After existing briefing/preferences loading, add:
email_context = []
adapters = get_email_adapters()
if adapters:
    try:
        from datetime import timedelta
        since = (session_date or date.today()) - timedelta(days=7)  # last 7 days of emails
        page = await adapters[0].list_emails(since=since)
        email_context = [
            {
                "message_id": e.message_id,
                "thread_id": e.thread_id,
                "subject": e.subject,
                "sender": e.sender,
                "recipient": e.recipient,
                "timestamp": e.timestamp.isoformat(),
            }
            for e in page.emails
        ]
    except Exception:
        logger.warning("initialize_session_state: could not load email context")
```

Add `import logging` and `logger = logging.getLogger(__name__)` at the top of session.py if not present.

Return the email_context in the dict:
```python
return {
    "briefing_narrative": briefing.narrative if briefing else "",
    "active_user_id": user_id,
    "preferences": preferences.model_dump(),
    "email_context": email_context,
}
```
  </action>
  <verify>
    <automated>cd /Users/jacobmarriott/Documents/Personal/dAIly && python -c "from daily.orchestrator.state import SessionState; s = SessionState(); assert hasattr(s, 'email_context'); assert s.email_context == []; print('OK')"</automated>
  </verify>
  <done>SessionState has email_context field defaulting to empty list. initialize_session_state populates it from email adapters when available.</done>
</task>

<task type="auto">
  <name>Task 2: Wire email metadata into DRAFT_SYSTEM_PROMPT and populate ActionDraft threading fields</name>
  <files>src/daily/orchestrator/nodes.py</files>
  <action>
**Update DRAFT_SYSTEM_PROMPT** (line 68-80) to include an `{email_context}` placeholder. Add it between the style examples and the user instruction:

```python
DRAFT_SYSTEM_PROMPT = (
    "You are a personal assistant drafting a {action_type} on behalf of the user.\n"
    "Match the user's writing style based on these recent sent emails:\n\n"
    "{style_examples}\n\n"
    "AVAILABLE EMAILS (use to identify the correct recipient and thread):\n"
    "{email_context}\n\n"
    "USER PREFERENCES: tone={tone}\n"
    "USER INSTRUCTION: {instruction}\n\n"
    "BRIEFING CONTEXT (for reference):\n{briefing_narrative}\n\n"
    "When the user wants to reply to an email, match their description to the correct "
    "email from the AVAILABLE EMAILS list and use that email's sender as the recipient. "
    "Include the thread_id and message_id from the matched email in your output.\n\n"
    "Output MUST be valid JSON with these fields:\n"
    '{{"recipient": "email@example.com or null", "subject": "Re: ... or null", '
    '"body": "the full draft text", "thread_id": "matched thread_id or null", '
    '"message_id": "matched message_id or null", '
    '"event_title": "null or title", '
    '"start_dt": "null or ISO datetime", "end_dt": "null or ISO datetime", '
    '"attendees": []}}'
)
```

**Add helper function** `_format_email_context` above `draft_node`:

```python
def _format_email_context(email_context: list[dict]) -> str:
    """Format email metadata list into a compact table for the LLM prompt."""
    if not email_context:
        return "(no emails available)"
    lines = []
    for i, e in enumerate(email_context, 1):
        lines.append(
            f"{i}. From: {e['sender']} | Subject: {e['subject']} | "
            f"thread_id: {e['thread_id']} | message_id: {e['message_id']}"
        )
    return "\n".join(lines)
```

**Update draft_node** (around line 392) to format and inject email_context into the prompt:

```python
email_context_str = _format_email_context(state.email_context)

system_content = DRAFT_SYSTEM_PROMPT.format(
    action_type=action_type.value.replace("_", " "),
    style_examples=style_examples or "(no style examples available)",
    email_context=email_context_str,
    tone=tone,
    instruction=instruction,
    briefing_narrative=briefing_narrative,
)
```

**Add fallback** if `state.email_context` is empty: before building the prompt, try fetching from adapter:

```python
# Fallback: if email_context is empty (e.g. non-briefing email), fetch live
email_ctx = state.email_context
if not email_ctx:
    adapters = get_email_adapters()
    if adapters:
        try:
            from datetime import timedelta
            since = datetime.now() - timedelta(days=7)
            page = await adapters[0].list_emails(since=since)
            email_ctx = [
                {
                    "message_id": e.message_id,
                    "thread_id": e.thread_id,
                    "subject": e.subject,
                    "sender": e.sender,
                    "recipient": e.recipient,
                    "timestamp": e.timestamp.isoformat(),
                }
                for e in page.emails
            ]
        except Exception as exc:
            logger.debug("draft_node: fallback email fetch failed: %s", exc)
            email_ctx = []
```

**Update ActionDraft construction** (around line 435) to populate thread_id and thread_message_id from LLM output:

```python
draft = ActionDraft(
    action_type=action_type,
    recipient=parsed.get("recipient") or None,
    subject=parsed.get("subject") or None,
    body=parsed.get("body") or "(no content)",
    thread_id=parsed.get("thread_id") or None,
    thread_message_id=parsed.get("message_id") or None,
    event_title=parsed.get("event_title") or None,
    start_dt=start_dt,
    end_dt=end_dt,
    attendees=attendees,
)
```

Note: The LLM outputs `message_id` (matching EmailMetadata field name) but ActionDraft stores it as `thread_message_id` (for RFC 2822 In-Reply-To header usage).
  </action>
  <verify>
    <automated>cd /Users/jacobmarriott/Documents/Personal/dAIly && python -c "
from daily.orchestrator.nodes import DRAFT_SYSTEM_PROMPT, _format_email_context
assert '{email_context}' in DRAFT_SYSTEM_PROMPT, 'Missing email_context placeholder'
assert 'thread_id' in DRAFT_SYSTEM_PROMPT, 'Missing thread_id in output schema'
result = _format_email_context([{'sender': 'a@b.com', 'subject': 'Test', 'thread_id': 't1', 'message_id': 'm1'}])
assert 'a@b.com' in result
assert 'thread_id: t1' in result
print('OK')
"</automated>
  </verify>
  <done>
- DRAFT_SYSTEM_PROMPT includes email_context section with instructions to match user intent to specific email
- LLM output schema includes thread_id and message_id fields
- draft_node formats state.email_context into prompt
- Fallback fetches from adapter if email_context is empty
- ActionDraft populated with thread_id and thread_message_id from LLM response
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| LLM output -> ActionDraft | LLM returns JSON that must be validated before constructing ActionDraft |
| Email metadata -> LLM prompt | Only metadata (sender, subject, IDs) enters the prompt -- no bodies (SEC-04) |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-QK-01 | Information Disclosure | email_context in SessionState | accept | Only metadata (sender, subject, IDs) stored -- no email bodies (SEC-04 maintained). LangGraph state is per-user scoped (T-03-04). |
| T-QK-02 | Tampering | LLM output thread_id/message_id | mitigate | Values are passed to GmailExecutor which validates against Gmail API -- invalid IDs cause API error, not security breach. Existing Pydantic validation on ActionDraft (T-04-08) rejects malformed fields. |
| T-QK-03 | Spoofing | LLM picks wrong recipient | accept | User approval gate (approval_node) shows recipient in card_text() preview before execution. User confirms or rejects. |
</threat_model>

<verification>
1. `python -c "from daily.orchestrator.state import SessionState; s = SessionState(); assert hasattr(s, 'email_context')"` -- SessionState has new field
2. `python -c "from daily.orchestrator.nodes import DRAFT_SYSTEM_PROMPT; assert '{email_context}' in DRAFT_SYSTEM_PROMPT"` -- Prompt includes email context
3. Manual test: `daily chat` -> "reply to [sender name]'s email" -> verify ActionDraft shows correct recipient, thread_id, thread_message_id in approval preview
</verification>

<success_criteria>
- draft_node LLM receives structured email metadata and can match user intent to correct email
- ActionDraft.recipient is populated with the matched sender's email address (not null)
- ActionDraft.thread_id and thread_message_id are populated for reply threading
- Fallback to live adapter fetch works when email_context is empty
- No email bodies enter the prompt or state (SEC-04 maintained)
</success_criteria>

<output>
After completion, create `.planning/quick/260412-gak-fix-null-recipient-in-draft-node-pass-em/260412-gak-SUMMARY.md`
</output>
