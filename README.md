# dAIly

A voice-first AI personal assistant that synthesises your digital life into an intelligent daily briefing. Connects to your email, calendar, and messaging — then delivers a prioritised, conversational summary every morning via a native iOS app.

## What it does

- **Morning briefing** — precomputed overnight, plays instantly on wake. No waiting for LLM or TTS at 6am.
- **Voice conversation** — ask follow-up questions, get summaries expanded, take actions — all by talking.
- **Action layer** — draft emails, create calendar events, and send messages with approval before anything sends.
- **Per-user onboarding** — connect Google, Microsoft, and Slack via OAuth from the iOS app.
- **Memory** — learns preferences over time ("make it shorter", "skip weather") and adapts future briefings.

## Architecture

```
iOS App (Swift + LiveKit)
    ↕ WebRTC (LiveKit)
LiveKit Agent Worker (Python)
    ↕
LangGraph Orchestrator
    ├── STT: Deepgram Nova-3
    ├── TTS: Cartesia Sonic-3
    ├── LLM: GPT-4.1 / GPT-4.1 mini
    └── Integrations: Google, Microsoft, Slack
    ↕
PostgreSQL + pgvector + Redis
```

The LLM never holds credentials. The backend mediates all external API calls. OAuth tokens are encrypted at rest with AES-256-GCM.

## Stack

| Layer | Technology |
|-------|-----------|
| iOS app | Swift, SwiftUI, LiveKit iOS SDK |
| Backend | Python, FastAPI, LangGraph |
| Voice STT | Deepgram Nova-3 |
| Voice TTS | Cartesia Sonic-3 |
| LLM | GPT-4.1, GPT-4.1 mini |
| Transport | LiveKit (WebRTC) |
| Database | PostgreSQL + pgvector |
| Cache | Redis |
| Auth | OAuth 2.0 (Google, Microsoft, Slack), magic-link pairing |
| Scheduler | APScheduler (async) |

## Project structure

```
├── src/daily/          # Python backend
│   ├── auth/           # Magic-link pairing, JWT auth
│   ├── integrations/   # Google, Microsoft, Slack OAuth + data fetch
│   ├── briefing/       # Briefing pipeline (ingest → summarise → TTS)
│   ├── agent/          # LangGraph orchestrator, LiveKit worker
│   └── models/         # SQLAlchemy models, Alembic migrations
├── ios/dAIly/          # Swift iOS app
│   ├── voice/          # LiveKit session, VAD, audio session
│   ├── onboarding/     # Onboarding flow, OAuth deep links
│   └── services/       # AuthService, API client
└── .planning/          # GSD planning artifacts
```

## Running locally

**Backend**

```bash
cp .env.example .env   # fill in API keys
docker compose up -d   # PostgreSQL + Redis
uv run alembic upgrade head
uv run python -m daily.main
```

**LiveKit worker**

```bash
uv run python -m daily.agent.worker dev
```

**iOS app**

Open `ios/dAIly.xcodeproj` in Xcode, set your development team, and run on a simulator or device.

## Tests

```bash
# Backend — unit + integration (80%+ coverage enforced)
uv run pytest --cov=src/daily/auth --cov=src/daily/integrations -q

# E2E smoke test
uv run pytest -m e2e -v

# iOS — open Xcode, run the dAIly scheme on iPhone 15 Simulator
```

## Milestones

| Version | What shipped |
|---------|-------------|
| v1.0 | MVP — briefing pipeline, voice interface, action layer |
| v1.1 | Intelligence layer — adaptive ranker, cross-session memory |
| v1.2 | Deployability — observability, Railway deploy |
| v1.3 | Voice polish — barge-in, backchannel, streaming TTS |
| v2.0 | Mobile — LiveKit WebRTC transport, native iOS + Android apps |
| v2.1 | TestFlight ready — per-user onboarding, OAuth, bug fixes, test coverage |

## Status

Currently in v2.1 (TestFlight preparation). Core voice loop is functional end-to-end on iOS. Next: adaptive learning, Apple integrations, production backend deploy.
