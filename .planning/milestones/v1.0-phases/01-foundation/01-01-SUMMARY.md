---
phase: "01-foundation"
plan: "01"
subsystem: "infrastructure"
tags: ["database", "encryption", "vault", "orm", "alembic", "docker", "tdd"]
dependency_graph:
  requires: []
  provides:
    - "async SQLAlchemy engine and session factory (make_engine, make_session_factory)"
    - "AES-256-GCM encrypt_token/decrypt_token functions"
    - "User and IntegrationToken ORM models"
    - "Alembic migration creating users and integration_tokens tables"
    - "pydantic-settings config with vault_key and integration credentials"
    - "Docker Compose services: postgres:15 and redis:7"
  affects: []
tech_stack:
  added:
    - "fastapi>=0.135.0"
    - "pydantic>=2.12.0 + pydantic-settings>=2.0.0"
    - "sqlalchemy>=2.0.49 (async)"
    - "asyncpg>=0.29.0"
    - "alembic>=1.13.0"
    - "cryptography>=42.0.0"
    - "greenlet>=3.3.2 (SQLAlchemy async compatibility)"
    - "python-dotenv>=1.0.0"
    - "typer>=0.24.0"
    - "google-auth-oauthlib, google-api-python-client, slack-sdk, msal, msgraph-sdk"
    - "pytest, pytest-asyncio>=1.0.0, httpx>=0.28.0"
  patterns:
    - "SQLAlchemy 2.0 DeclarativeBase + Mapped + mapped_column pattern"
    - "AES-256-GCM with random 12-byte nonce prepended to ciphertext in base64"
    - "Alembic async migration using run_sync(do_run_migrations) over AsyncConnection"
    - "pydantic-settings BaseSettings with env_file=.env for configuration"
key_files:
  created:
    - "pyproject.toml"
    - "docker-compose.yml"
    - ".env.example"
    - ".gitignore"
    - "src/daily/__init__.py"
    - "src/daily/config.py"
    - "src/daily/db/__init__.py"
    - "src/daily/db/engine.py"
    - "src/daily/db/models.py"
    - "src/daily/vault/__init__.py"
    - "src/daily/vault/crypto.py"
    - "alembic.ini"
    - "alembic/env.py"
    - "alembic/versions/001_initial_schema.py"
    - "tests/conftest.py"
    - "tests/test_vault.py"
    - "tests/test_schema.py"
  modified: []
decisions:
  - "greenlet added as explicit dependency — required by SQLAlchemy async engine at runtime despite not being listed in SQLAlchemy's install_requires for non-asyncio contexts"
  - "uv pip install -e . used for editable install in worktree — uv sync alone did not populate the pth file with the src/ path"
  - "config.py database_url has a default value to avoid required-field validation error when VAULT_KEY is also empty during tests"
metrics:
  duration_minutes: 5
  completed_date: "2026-04-05"
  tasks_completed: 2
  tasks_total: 2
  files_created: 17
  files_modified: 0
  tests_added: 14
  tests_passing: 14
---

# Phase 01 Plan 01: Project Scaffold, DB Schema, and Vault Summary

**One-liner:** Project scaffold with async SQLAlchemy 2.0 ORM, AES-256-GCM token vault, Alembic migration, and 14 passing tests enforcing SEC-01 and SEC-04.

## What Was Built

Task 1 established the entire project foundation: `pyproject.toml` with all Phase 1 dependencies via `uv`, Docker Compose running `postgres:15` and `redis:7`, async SQLAlchemy ORM models for `users` and `integration_tokens` (no raw_body columns per SEC-04/D-06), and an Alembic async migration that has been applied to the running database.

Task 2 implemented the AES-256-GCM token vault: `encrypt_token(plaintext, key) -> str` and `decrypt_token(encrypted, key) -> str` using a fresh 96-bit nonce per encryption call. Key length validation (ValueError on non-32-byte keys) and GCM authentication tag (InvalidTag on wrong key or tampered ciphertext) are enforced. Eight vault tests and six schema privacy tests all pass.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] greenlet missing for SQLAlchemy async engine**
- **Found during:** Task 1 — Alembic upgrade head failed at runtime
- **Issue:** `sqlalchemy.util.concurrency` requires `greenlet` for async engine operations; it is not automatically installed with `sqlalchemy[asyncio]` when using `uv add sqlalchemy`
- **Fix:** Added `greenlet>=3.3.2` to project dependencies via `uv add greenlet`
- **Files modified:** `pyproject.toml`, `uv.lock`
- **Commit:** acd4d16

**2. [Rule 3 - Blocking] Editable install not auto-activated by uv sync**
- **Found during:** Task 1 — `ModuleNotFoundError: No module named 'daily'` after `uv sync`
- **Issue:** `uv sync` installs the package but the `_daily.pth` file in site-packages was empty, not pointing to `src/`. The `daily` module was not on `sys.path`.
- **Fix:** Ran `uv pip install -e .` to create a proper editable install pointing to `src/daily`
- **Files modified:** none (runtime fix; uv.lock unchanged)
- **Commit:** acd4d16

## Known Stubs

None — all exported symbols are fully implemented.

## Threat Flags

No new threat surface introduced beyond the plan's threat model. All T-1-01 through T-1-05 mitigations implemented as specified.

## Self-Check: PASSED

Files exist:
- FOUND: src/daily/vault/crypto.py
- FOUND: src/daily/db/models.py
- FOUND: src/daily/db/engine.py
- FOUND: alembic/versions/001_initial_schema.py
- FOUND: tests/test_vault.py
- FOUND: tests/test_schema.py

Commits exist:
- acd4d16 — feat(01-01): project scaffold, config, DB schema, and Alembic migration
- 77514a3 — feat(01-01): AES-256-GCM token vault with tests

Tests: 14 passed, 0 failed
