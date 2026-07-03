# Ops Runbook — Deployment, Backups, Monitoring

This is the operational reference for running dAIly in production. It covers
what `docker-compose.prod.yml` automates today, and the infra decisions that
still need a human call (marked **DECISION NEEDED**).

---

## 1. Deployment topology

`docker-compose.prod.yml` is runnable as-is on a single VM:

```bash
cp .env.example .env   # fill in real values — see .env.example for the full list
docker compose -f docker-compose.prod.yml up -d
```

Services, in dependency order:

1. **postgres**, **redis** — self-hosted, local volumes.
2. **migrate** — one-shot `alembic upgrade head`, must complete before `api`/`worker` start.
3. **api** — FastAPI app, production uvicorn command (no `--reload`), health-checked via `GET /health`.
4. **worker** — LiveKit agent worker, health-checked via `pgrep`.
5. **livekit**, **coturn** — voice transport + NAT traversal relay.
6. **caddy** — reverse proxy in front of `api`, automatic Let's Encrypt TLS for `DOMAIN`.

`pg-backup` is opt-in (see §3) via `--profile backup`.

### Recommended beta path — managed infra (DECISION NEEDED)

Self-hosting postgres/redis/livekit/coturn on one VM is the fastest way to get
a real deployment running, but it means:

- No automatic failover, point-in-time recovery, or read replicas for Postgres.
- Redis data loss on container/volume loss unless you configure AOF/RDB persistence tuning yourself.
- coturn/LiveKit self-hosting requires you to own NAT traversal correctness and TURN server capacity planning.

**Recommendation for the beta:** move to managed infra —

| Component | Managed option | Tradeoff |
|---|---|---|
| Postgres | Neon, Supabase, or Railway Postgres | Small monthly cost; gets you PITR, automated backups, connection pooling for free. Update `DATABASE_URL`/`DATABASE_URL_PSYCOPG` and drop the `postgres`/`pg-backup` services. |
| Redis | Upstash or Railway Redis | Small monthly cost; gets you persistence and monitoring without operating Redis yourself. Update `REDIS_URL` and drop the `redis` service. |
| LiveKit + TURN | LiveKit Cloud | Removes the entire `livekit` + `coturn` self-hosting burden (NAT traversal, TURN server capacity, LiveKit version upgrades) at a usage-based cost. Update `LIVEKIT_URL`/`LIVEKIT_API_KEY`/`LIVEKIT_API_SECRET` to the Cloud project's values and drop the `livekit`/`coturn` services entirely. |

This is a go/no-go call for Jacob — self-hosted is fully wired and cheaper at
zero/low traffic; managed is less ops burden and the safer default once real
users are on it.

---

## 2. Secrets and TLS

- `DOMAIN` must be a real, publicly resolvable hostname pointing at the VM's
  IP before starting `caddy` — it needs to complete an ACME challenge on
  ports 80/443.
- `TURN_SECRET` / `TURN_REALM` — generate a real secret
  (`openssl rand -hex 32` or similar) and set `TURN_REALM` to `DOMAIN`.
  `scripts/coturn-entrypoint.sh` refuses to start if either is left as the
  tracked placeholder (`REPLACE_TURN_SECRET`/`REPLACE_DOMAIN`).
- Run `bash scripts/check-secrets.sh` before every deploy (also runs in CI as
  the `secrets-scan` job) to catch known-bad secret values in tracked files.
- Full env var list: `.env.example`.

---

## 3. Backups

### Self-hosted Postgres

`docker-compose.prod.yml` includes an opt-in `pg-backup` service: a
`pg_dump -F c` loop, once every 24h, retained 14 days, written to the
`pgbackups` named volume.

Start it:

```bash
docker compose -f docker-compose.prod.yml --profile backup up -d pg-backup
```

Restore from a dump:

```bash
docker compose -f docker-compose.prod.yml exec postgres \
  pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists /backups/<file>.dump
```

**This is a local-disk backup only** — if the VM is lost, the backups go with
it. For anything beyond a personal/dev deployment, either:

- Mount `pgbackups` on a volume that's itself backed up off-host (e.g. a
  cloud block-storage snapshot policy), or
- Switch to a managed Postgres provider and rely on its built-in
  point-in-time recovery instead of `pg-backup` (see §1).

### Self-hosted Redis

Redis here holds cache/session state (briefing cache, TTL data), not durable
records — data loss on restart is an acceptable/expected failure mode. No
backup service is provided for it.

---

## 4. Monitoring (DECISION NEEDED — needs a Sentry DSN + uptime tool from Jacob)

### Error tracking — Sentry

Not wired up (no SDK added — would be a new PyPI dependency, out of this
pass's scope per the package-install-safety policy). To add it:

1. Create a Sentry project, get a DSN.
2. Add `SENTRY_DSN` to `.env` / `.env.example`.
3. Add the `sentry-sdk[fastapi]` dependency via `uv add` (run it through the
   standard package-vetting checklist first) and initialize it in
   `src/daily/main.py`'s app startup — out of this pass's file scope
   (`src/` is owned by another agent).

### Uptime checks

Point an external uptime monitor (e.g. UptimeRobot, Better Uptime, or a
simple cron + curl + alert) at:

```
GET https://<DOMAIN>/health
```

Expected: `200 {"status": "ok"}`. Alert on non-200 or timeout. This is the
cheapest possible signal that `caddy` → `api` → app process is alive; it does
not check Postgres/Redis/worker/LiveKit connectivity — those would need
either a richer `/health` implementation (out of scope here, owned by the
backend agent) or separate checks against `pg-backup`'s last-success
timestamp and the `worker` container's health status.

---

## 5. CI

`.github/workflows/ci.yml` runs on every push/PR:

- `backend`: installs deps with `uv`, runs migrations against a real
  `pgvector/pgvector:pg15` service container, runs the unit/integration
  suite with coverage enforced (`fail_under = 80` in `pyproject.toml`),
  then runs the `e2e`-marked suite separately.
- `secrets-scan`: `scripts/check-secrets.sh` against tracked files.
- `ios`: unsigned simulator build of the dAIly scheme on `macos-15`,
  `continue-on-error: true` — no shared Xcode scheme was found checked into
  `ios/dAIly.xcodeproj` at the time this was written, so scheme discovery in
  CI is unverified. Un-mark it as non-blocking once a run has been observed
  to pass.

---

## 6. Still needs a human

- Rotate/generate real values for every `CHANGE_ME_*` placeholder in
  `.env.example` before first deploy (`VAULT_KEY`, `JWT_SECRET`,
  `TURN_SECRET`, all OAuth client secrets, `LIVEKIT_API_KEY`/`SECRET`, etc.)
  in the actual provider dashboards.
- Pick and provision `DOMAIN` (DNS A/AAAA record → the VM's public IP)
  before starting `caddy`.
- Managed vs. self-hosted infra go/no-go (§1).
- Sentry DSN + decision on whether to add the SDK now or defer (§4).
- Choice of uptime-check provider (§4).
