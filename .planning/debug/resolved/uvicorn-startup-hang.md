---
status: resolved
trigger: "Uvicorn hangs on startup after recent code changes"
created: 2026-05-06T00:00:00Z
updated: 2026-05-06T01:00:00Z
---

## Current Focus

hypothesis: CONFIRMED — Stale uvicorn process (PID 22260) from a previous dev session is holding port 8000. The reloader starts but the worker subprocess cannot bind to port 8000, so it silently hangs/dies.
test: Kill PID 22260 (and parent PID 22257). Restart uvicorn.
expecting: "Application startup complete" appears within a few seconds of starting.
next_action: Fix applied — awaiting human verification.

## Symptoms

expected: Uvicorn starts, prints "Application startup complete", serves requests
actual: Uvicorn reloader starts but worker process never starts — hangs indefinitely after "Started reloader process"
errors: |
  INFO: Started reloader process [XXXX] using WatchFiles
  (hangs here — no "Application startup complete")
  Import isolation tests show non-deterministic hang — sometimes individual imports complete, sometimes they hang
reproduction: PYTHONPATH=src uv run uvicorn daily.main:app --reload --reload-dir src
started: After subagent made code changes in this dev session

## Eliminated

- hypothesis: connect_args={"timeout": 5} on asyncpg causes a hang at import time
  evidence: asyncpg.connect() DOES accept `timeout` as a valid kwarg. import daily.db.engine completes in 0.11-0.16s. Engine creation is lazy — no connection until first use.
  timestamp: 2026-05-06

- hypothesis: Python logic error or blocking call in changed code causes hang
  evidence: All changed files import cleanly in <0.5s each. Full main.py import sequence completes in <2s total. Changes are functional logic only (PKCE, vault_key decoding, narrator prompt update).
  timestamp: 2026-05-06

- hypothesis: daily.briefing.scheduler or daily.integrations.router import hangs
  evidence: Both complete in <0.3s in all isolated and combined tests.
  timestamp: 2026-05-06

## Evidence

- timestamp: 2026-05-06
  checked: lsof -i :8000
  found: PID 22260 python3 uvicorn daily.main:app --host 0.0.0.0 --port 8000 is LISTENING on port 8000. Has been running since Thursday 2PM.
  implication: Port 8000 is occupied by a stale process. New uvicorn worker cannot bind.

- timestamp: 2026-05-06
  checked: ps aux for PID 22260 and 22257
  found: uv run uvicorn daily.main:app --host 0.0.0.0 --port 8000 (no --reload flag, started Thursday)
  implication: Old development session left uvicorn running. It still holds the socket.

- timestamp: 2026-05-06
  checked: complete main.py import sequence test
  found: All imports complete in <0.5s each, total <2s. No Python-level hang.
  implication: The hang is at the OS/network level (port binding), not Python logic.

- timestamp: 2026-05-06
  checked: uvicorn reload architecture
  found: Reloader process starts first and does NOT bind to the port — it forks the worker. The worker subprocess tries to bind to port 8000. If port is taken, the worker fails/hangs silently without printing "Application startup complete".
  implication: "Started reloader process" appears but "Application startup complete" never prints = worker cannot bind.

## Resolution

root_cause: Stale uvicorn process (PID 22260, parent 22257) from a prior dev session is holding port 8000. When the new uvicorn starts with --reload, the reloader process starts (prints "Started reloader process") but the forked worker subprocess cannot bind to port 8000 and silently fails. The recent code changes (PKCE in integrations/router.py, connect_args in db/engine.py, vault_key base64 decode in auth/router.py) are all correct and are NOT the cause.
fix: Kill PIDs 22257 and 22260. Restart uvicorn normally.
verification: |
  Killed PIDs 22260 and 22257 (already dead). Ran uvicorn with --reload. Output:
    INFO: Started reloader process [50508] using WatchFiles
    INFO: Started server process [50510]
    INFO: Waiting for application startup.
    INFO: Application startup complete.
  Issue fully resolved — no code changes required.
files_changed: []
