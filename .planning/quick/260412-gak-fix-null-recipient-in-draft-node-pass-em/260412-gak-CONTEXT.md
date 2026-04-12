# Quick Task 260412-gak: Fix null recipient in draft_node — Context

**Gathered:** 2026-04-12
**Status:** Ready for planning

<domain>
## Task Boundary

Fix null recipient in draft_node — pass email metadata to LLM prompt. The LLM currently has no structured email data (sender address, thread_id, message_id) when drafting replies, so it outputs recipient=null. Need to make email metadata available and have the LLM select the correct recipient.

</domain>

<decisions>
## Implementation Decisions

### Data source for email metadata
- **Hybrid approach**: Store structured email metadata in SessionState during session init (from BriefingContext), AND fallback to re-fetching from Gmail adapter at draft time if the target email isn't in the briefing set.
- Rationale: Briefing emails are instant (already loaded), but user may want to reply to non-briefing emails too.

### Matching user intent to specific email
- **LLM picks from structured list**: Pass the email metadata list (sender, subject, thread_id, message_id) into the draft prompt. Let GPT-4.1 match the user's description to the right email.
- **Fallback: ask user if unsure**: If the LLM can't confidently match (e.g. ambiguous description, multiple candidates), it should indicate uncertainty and the system should ask the user to confirm which email.

### Gmail reply threading
- **Full threading**: Populate thread_id and thread_message_id on ActionDraft so replies land in the correct Gmail thread (In-Reply-To header). EmailMetadata already carries thread_id and message_id.

### Claude's Discretion
- Implementation details of how "LLM is unsure" is signalled (e.g. confidence field in JSON output, or a special "ambiguous" recipient value)
- Exact format of email metadata in the prompt (compact table vs structured list)

</decisions>

<specifics>
## Specific Ideas

- SessionState gets a new field: `email_context: list[EmailMetadata]` populated during session init from BriefingContext.emails
- DRAFT_SYSTEM_PROMPT gets an `{email_context}` placeholder with structured sender/subject/thread data
- JSON output schema adds thread_id and message_id fields
- draft_node: if no match found in state.email_context, call list_emails() as fallback
- ActionDraft construction populates thread_id and thread_message_id from matched email

</specifics>

<canonical_refs>
## Canonical References

- `src/daily/orchestrator/state.py` — SessionState definition (line 24-44)
- `src/daily/orchestrator/nodes.py` — DRAFT_SYSTEM_PROMPT (line 68-80), draft_node (line 340-461)
- `src/daily/integrations/models.py` — EmailMetadata (line 14-23), has sender, thread_id, message_id
- `src/daily/briefing/models.py` — BriefingContext (line 41-53), RankedEmail (line 19-24)
- `src/daily/actions/base.py` — ActionDraft (line 57-90), already has thread_id and thread_message_id fields

</canonical_refs>
