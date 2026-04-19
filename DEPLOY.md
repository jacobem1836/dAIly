# Deploying dAIly

Single-host VPS deployment using Docker Compose and Caddy.

## Prerequisites

- A VPS running Ubuntu 22.04+ with Docker and Docker Compose installed
- A domain name with an A record pointed at the VPS public IP
- API keys: OpenAI, Deepgram, Cartesia, and OAuth credentials for any integrations you want active

**Install Docker on Ubuntu if not already present:**

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# Log out and back in for group change to take effect
```

## 1. Clone and configure

```bash
git clone https://github.com/jacobmarriott/dAIly.git
cd dAIly
cp .env.example .env
```

Open `.env` and fill in all required values. The file is fully commented — every variable has a description and, where relevant, shows both the local dev variant and the Docker Compose variant.

**Critical:** For Docker Compose, the database and Redis URLs must use service names as hostnames, not `localhost`. Update these three lines in `.env`:

```bash
DATABASE_URL=postgresql+asyncpg://daily:daily_dev@postgres:5432/daily
DATABASE_URL_PSYCOPG=postgresql://daily:daily_dev@postgres:5432/daily
REDIS_URL=redis://redis:6379/0
```

Generate a random `VAULT_KEY` (required for encrypting OAuth tokens):

```bash
python3 -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())"
```

Paste the output into `.env` as the value for `VAULT_KEY`.

## 2. Bind the app to loopback only

The `docker-compose.yml` ships with the app port bound to all interfaces (`8000:8000`). On a VPS, Caddy handles the public-facing connection — the app should not be directly reachable from the internet.

Edit `docker-compose.yml` and change the `app` ports entry:

```yaml
# Before (local dev):
ports:
  - "8000:8000"

# After (VPS production):
ports:
  - "127.0.0.1:8000:8000"
```

This binds port 8000 to the loopback interface only. Caddy proxies from port 443 to `localhost:8000`. Port 8000 is not accessible from outside the VPS.

## 3. Start the stack

```bash
docker compose up -d
```

The stack starts three services: `postgres`, `redis`, and `app`. The app container runs Alembic migrations before starting uvicorn — this is handled automatically by the entrypoint script.

Wait for the app to be ready:

```bash
docker compose logs -f app
# Wait until you see: "Application startup complete."
# Press Ctrl+C to stop following logs
```

Verify all services are healthy:

```bash
docker compose ps
```

All three services should show `running` or `healthy` status. If `app` shows `exiting`, check logs:

```bash
docker compose logs app
```

Common cause: missing or incorrect values in `.env`. Fix the value and run `docker compose up -d` again.

## 4. Install Caddy

Caddy handles HTTPS automatically — it obtains and renews TLS certificates from Let's Encrypt with no additional configuration. There is no certbot, no cron job, and no manual certificate management.

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install -y caddy
```

Verify Caddy is running:

```bash
sudo systemctl status caddy
```

## 5. Configure Caddy

Create or replace the default Caddyfile with your domain:

```bash
sudo nano /etc/caddy/Caddyfile
```

Replace the contents with:

```caddyfile
yourdomain.com {
    reverse_proxy localhost:8000
}
```

Replace `yourdomain.com` with your actual domain. Save and close.

Reload Caddy to apply the configuration:

```bash
sudo systemctl reload caddy
```

Caddy will immediately begin the ACME challenge to obtain a TLS certificate from Let's Encrypt. This requires:
- Your domain's A record is already pointing at the VPS public IP
- Port 80 and 443 are open in your VPS firewall

Check Caddy logs if the certificate does not come up within a minute:

```bash
sudo journalctl -u caddy -f
```

## 6. Smoke test

Verify the deployment is working end-to-end:

```bash
curl https://yourdomain.com/health
```

Expected response:

```json
{"status": "ok", "db": "ok", "redis": "ok", "scheduler": "running"}
```

If you get a TLS error, wait 30–60 seconds for Caddy to finish obtaining the certificate and retry. If you get a 502 or connection refused, check that the app container is running (`docker compose ps`) and that the Caddyfile points to `localhost:8000`.

## Maintenance

### View logs

```bash
# Follow app logs
docker compose logs -f app

# Follow all services
docker compose logs -f

# Last 100 lines
docker compose logs --tail=100 app
```

### Restart the app

```bash
docker compose restart app
```

### Deploy an update

```bash
git pull
docker compose up --build -d
```

This rebuilds the app image with the latest code, then restarts only the containers that changed. Postgres and Redis data are preserved in named volumes.

### Backup the database

```bash
docker compose exec postgres pg_dump -U daily daily > backup-$(date +%Y%m%d).sql
```

Restore from backup:

```bash
docker compose exec -T postgres psql -U daily daily < backup-20260101.sql
```

### Stop the stack

```bash
docker compose down
```

Volumes are preserved. Add `--volumes` to also remove the Postgres data volume (destructive — use only if you want a clean slate).

### Environment variable changes

After editing `.env`, restart the app service to pick up the new values:

```bash
docker compose up -d app
```

## Security notes

- `.env` is never committed to git (`.gitignore` includes `.env`). Keep it secure on the VPS.
- Set restrictive file permissions on `.env`:

  ```bash
  chmod 600 .env
  ```

- The app port (8000) is bound to `127.0.0.1` — it is only accessible via Caddy on port 443. Verify your VPS firewall allows ports 80 and 443 only from the public internet.
- OAuth tokens are encrypted at rest using AES-256-GCM. The `VAULT_KEY` is the only secret that must never be lost — if you rotate it, all stored OAuth tokens become unreadable and users must re-authorise.
