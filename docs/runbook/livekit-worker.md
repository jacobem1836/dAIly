# LiveKit Worker Runbook

## Symptom

iOS shows one of these errors on the voice screen:

- "Couldn't open a voice session — the worker may not be running."
- "Voice agent didn't join — the worker may not be running, or LIVEKIT_URL is misconfigured. Check the runbook."
- "Voice server rejected the connection. The worker may be offline or misconfigured."
- Any variation of "Couldn't connect to voice."

## Diagnostic Steps

### Step 1 – Confirm the worker process is running

```bash
ps aux | grep -E "daily.worker|livekit.agents" | grep -v grep
```

Expected: at least one matching process line.

If empty, start the worker:

```bash
python -m daily.worker dev
```

> **Tip:** For a dev session that survives terminal close, run under `nohup` or inside a `tmux` session:
> ```bash
> tmux new-session -d -s worker 'python -m daily.worker dev'
> ```

---

### Step 2 – Confirm the worker `.env` has all three LiveKit variables

```bash
grep -E "^LIVEKIT_URL|^LIVEKIT_API_KEY|^LIVEKIT_API_SECRET" .env
```

Expected output — all three present:

```
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=APIxxxxxxxxxx
LIVEKIT_API_SECRET=xxxxxxxxxxxxxxxxxxxxxxxx
```

- `LIVEKIT_URL` must be a `wss://` LiveKit Cloud (or self-hosted) URL.
- It must **not** be the FastAPI tunnel URL — that is a different service.
- If any variable is missing, add it to `.env` and restart the worker.

---

### Step 3 – Verify the LIVEKIT_URL host is reachable

Replace `wss://` with `https://` and test with curl:

```bash
curl -sI https://your-project.livekit.cloud
```

Expected: `HTTP/1.1 200 OK` or `HTTP/1.1 426 Upgrade Required`.

Any other response (DNS error, connection refused, timeout) means the URL is wrong or the LiveKit server is down. Double-check the value in `.env` against your LiveKit Cloud project dashboard.

---

### Step 4 – Verify `/livekit/token` returns a token tied to the correct URL

Get a valid access token from the device's Keychain (or via a fresh login) and run:

```bash
curl -s \
  -H "Authorization: Bearer <access_token>" \
  https://<your-tunnel>/livekit/token | python3 -m json.tool
```

Confirm that the `url` field in the response matches `LIVEKIT_URL` exactly. A mismatch means the FastAPI backend is reading a stale or wrong environment variable — restart the FastAPI server after fixing `.env`.

---

### Step 5 – Check worker logs for agent-join confirmation

With the worker running, attempt a voice connection from iOS. Watch the worker output for:

```
room subscribed
agent joined
```

If neither line appears within ~15 seconds, the worker is running but not connecting to the same LiveKit room. The most common causes:

1. `LIVEKIT_URL` in `.env` does not match the URL the iOS token is pointing at.
2. `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET` mismatch — the worker can't authenticate to the room.
3. Worker crashed silently — check for a Python traceback above the last log line.

---

## Most Common Root Cause

**The worker was killed when the terminal closed.**

The worker is a foreground Python process. Closing the terminal window or ending the SSH session terminates it. The iOS client connects to LiveKit successfully (room exists) but no agent ever joins the room, so the 60-second agent-join timeout fires.

**Fix:** Always run the worker under `tmux`, `screen`, or `nohup` for anything beyond a one-shot test:

```bash
nohup python -m daily.worker dev > /tmp/daily-worker.log 2>&1 &
```

or

```bash
tmux new-session -s worker 'python -m daily.worker dev'
```
