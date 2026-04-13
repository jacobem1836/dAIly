---
status: verifying
trigger: "Fix issue: chat-openai-missing-key-traceback"
created: 2026-04-08T00:00:00Z
updated: 2026-04-08T00:00:00Z
---

## Current Focus

hypothesis: AsyncOpenAI() constructor raises OpenAIError outside the try/except in respond_node, propagating unhandled through _run_chat_session
test: Code inspection confirmed line 86 (constructor) precedes line 87 (try block)
expecting: Wrapping run_session call in _run_chat_session with OpenAI-specific exception handler will surface a clean message
next_action: Add try/except around run_session in cli.py _run_chat_session

## Symptoms

expected: Chat fails gracefully with a clear error message when OPENAI_API_KEY is missing
actual: Chat launches and shows 'You: ' prompt, but typing a message crashes with traceback: OpenAIError missing OPENAI_API_KEY
errors: OpenAIError traceback when sending a message without OPENAI_API_KEY set
reproduction: Run `PYTHONPATH=src uv run daily chat` without OPENAI_API_KEY in env, then type a message
started: Since Phase 03 chat implementation

## Eliminated

- hypothesis: OpenAIError raised inside existing try/except in respond_node
  evidence: Constructor call `client = AsyncOpenAI()` on line 86 is OUTSIDE the try block at line 87; constructor raises before any exception handler
  timestamp: 2026-04-08

## Evidence

- timestamp: 2026-04-08
  checked: src/daily/orchestrator/nodes.py respond_node lines 86-102
  found: AsyncOpenAI() constructor on line 86 is outside the try/except block starting at line 87; OpenAIError from missing key propagates up unhandled
  implication: The fix must be in the caller (_run_chat_session in cli.py) to catch and display a clean error message per instructions

- timestamp: 2026-04-08
  checked: src/daily/cli.py _run_chat_session lines 527-541
  found: run_session call has no exception handler; any OpenAI-related error from the graph propagates to the top-level asyncio.run() call
  implication: Adding try/except around the run_session call in the while loop is the correct minimal fix

## Resolution

root_cause: AsyncOpenAI() constructor in respond_node (nodes.py:86) is called outside the try/except block; a missing OPENAI_API_KEY causes it to raise openai.OpenAIError which propagates unhandled through run_session up to _run_chat_session
fix: Wrap the run_session call in _run_chat_session's while loop with try/except for openai.OpenAIError; print a clean error message and break out of the loop
verification: pending
files_changed: [src/daily/cli.py]
