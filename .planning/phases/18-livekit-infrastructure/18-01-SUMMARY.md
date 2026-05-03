---
phase: 18-livekit-infrastructure
plan: "01"
subsystem: infrastructure
tags: [livekit, docker, coturn, turn, webrtc, pydantic-settings]
dependency_graph:
  requires: []
  provides: [livekit-dev-compose, livekit-prod-compose, coturn-config, livekit-settings, livekit-api-sdk]
  affects: [18-02, 18-03]
tech_stack:
  added: [livekit-api>=1.1.0, livekit/livekit-server:v1.11.0, coturn/coturn:4.6.2]
  patterns: [pydantic-settings env loading, docker-compose service extension, TURN relay with static-auth-secret]
key_files:
  created:
    - docker-compose.prod.yml
    - livekit.yaml
    - turnserver.conf
    - tests/test_livekit_connectivity.py
  modified:
    - docker-compose.yml
    - pyproject.toml
    - src/daily/config.py
    - .env.example
decisions:
  - "Quoted LIVEKIT_KEYS env var in docker-compose.yml to avoid YAML map parse error (colon-space in value)"
  - "Used network_mode: host for prod compose per RESEARCH.md Pitfall 2 (Linux VPS ICE candidate binding)"
  - "Embedded TURN disabled in livekit.yaml (turn.enabled: false); external Coturn handles relay per Pitfall 5"
  - "Pinned coturn:4.6.2 to avoid latest-tag drift"
metrics:
  duration: "~15 minutes"
  completed: "2026-04-28"
  tasks_completed: 3
  files_created: 4
  files_modified: 4
---

# Phase 18 Plan 01: LiveKit Infrastructure Summary

**One-liner:** Self-hosted LiveKit dev+prod Docker Compose with Coturn TURN relay, livekit-api SDK installed, and Pydantic Settings extended with LiveKit URL/key/secret.

## What Was Built

### Task 1 — LiveKit dev service + livekit-api dependency

Added `livekit/livekit-server:v1.11.0` as a new service to the existing `docker-compose.yml` alongside Postgres and Redis. The service binds ports 7880 (WebSocket signal) and 7881 (TCP media) and registers a dev API key pair via `LIVEKIT_KEYS`. Added `livekit-api>=1.1.0` to `pyproject.toml` and ran `uv sync` to install. Extended `.env.example` with LIVEKIT_URL, LIVEKIT_API_KEY, and LIVEKIT_API_SECRET dev defaults.

### Task 2 — Settings extension + production manifests

Extended `src/daily/config.py` `Settings` class with three new fields: `livekit_url`, `livekit_api_key`, `livekit_api_secret` (all with safe dev defaults, loaded from environment via Pydantic BaseSettings).

Created three new files:
- `docker-compose.prod.yml` — production LiveKit + Coturn stack with `network_mode: host` for Linux VPS ICE candidate binding
- `livekit.yaml` — production LiveKit config with `use_external_ip: true`, RTC UDP port range 50000-60000, and REPLACE_API_KEY/REPLACE_API_SECRET placeholders forcing operator action at deploy time
- `turnserver.conf` — Coturn configuration with `lt-cred-mech`, `use-auth-secret`, and `static-auth-secret=REPLACE_TURN_SECRET` placeholder

Appended `TURN_SECRET` and `TURN_REALM` placeholders to `.env.example`.

### Task 3 — Smoke tests (TDD)

Created `tests/test_livekit_connectivity.py` with two tests:
- `test_livekit_dev_container_reachable` — HTTP GET to localhost:7880, skips gracefully if container not running (CI-safe)
- `test_livekit_access_token_signs` — mints a JWT via the `livekit-api` SDK with dev key/secret; verifies JWT format (3-part dot-delimited string)

Result: 1 passed, 1 skipped (container not running in dev environment without docker compose up).

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | 91da568 | feat(18-01): add LiveKit dev service to docker-compose and install livekit-api |
| 2 | dd7dbea | feat(18-01): extend Settings with LiveKit config and add production compose with Coturn |
| 3 | 9539909 | test(18-01): smoke tests for LiveKit SDK and dev container reachability |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed YAML parse error in LIVEKIT_KEYS env var**
- **Found during:** Task 1 verification (`docker compose config` returning parse error)
- **Issue:** The plan specified `- LIVEKIT_KEYS=devkey: secret` as a bare YAML list item. YAML parses `devkey: secret` as a map (colon+space is a key-value separator), causing `docker compose config` to fail with "unexpected type map[string]interface{}"
- **Fix:** Quoted the value as `- "LIVEKIT_KEYS=devkey: secret"` so YAML treats it as a string
- **Files modified:** docker-compose.yml
- **Commit:** 91da568

## Known Stubs

None — all config fields have functional dev defaults. Production placeholder values (`REPLACE_API_KEY`, `REPLACE_TURN_SECRET`, `REPLACE_DOMAIN`) are intentional operator-action gates, not stubs.

## Threat Flags

No new security surface beyond what the plan's threat model documented. T-18-01 through T-18-04 mitigations are all in place:
- API key/secret loaded from env vars only (never committed)
- Coturn uses `lt-cred-mech` + `use-auth-secret` (T-18-02)
- `use_external_ip: true` in livekit.yaml (T-18-03)
- Production compose uses `--config` not `--dev`; keys block has placeholder forcing operator replacement (T-18-04)

## Self-Check: PASSED

- [x] docker-compose.yml contains `livekit/livekit-server:v1.11.0` — FOUND
- [x] docker-compose.prod.yml exists — FOUND
- [x] livekit.yaml exists with `use_external_ip: true` — FOUND
- [x] turnserver.conf exists with `static-auth-secret=` — FOUND
- [x] src/daily/config.py contains `livekit_url: str` — FOUND
- [x] tests/test_livekit_connectivity.py exists — FOUND
- [x] Commit 91da568 — FOUND
- [x] Commit dd7dbea — FOUND
- [x] Commit 9539909 — FOUND
