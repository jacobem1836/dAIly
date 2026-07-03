#!/usr/bin/env bash
# Fails if known-bad secret values or obvious real-secret patterns show up in
# git-tracked files. Run locally with `bash scripts/check-secrets.sh`; wired
# into CI as the `secrets-scan` job (.github/workflows/ci.yml).
#
# Two patterns below are intentionally allowlisted in specific files because
# those files are meant to contain them as non-production dev/template
# values, not as leaked secrets:
#   - devsecret12345678901234567890123: the LiveKit dev-mode server secret,
#     legitimate in livekit.yaml and docker-compose.yml (local dev only,
#     never used in docker-compose.prod.yml).
#   - REPLACE_TURN_SECRET / REPLACE_DOMAIN: the coturn config template
#     placeholders, legitimate in turnserver.conf. scripts/coturn-entrypoint.sh
#     refuses to start a real container if these are still unsubstituted at
#     runtime — this script only guards against them appearing elsewhere.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

fail=0

# Usage: check_pattern <grep -E pattern> <description> [allowlisted files...]
check_pattern() {
  local pattern="$1"
  local description="$2"
  shift 2

  local pathspecs=(".")
  local f
  for f in "$@"; do
    pathspecs+=(":(exclude)${f}")
  done

  local matches
  matches="$(git grep -nIE "$pattern" -- "${pathspecs[@]}" 2>/dev/null || true)"
  if [ -n "$matches" ]; then
    echo "FAIL: found ${description} in tracked files:"
    echo "$matches"
    echo
    fail=1
  fi
}

check_pattern \
  'devsecret12345678901234567890123' \
  'the public LiveKit dev-mode secret' \
  'livekit.yaml' 'docker-compose.yml' 'scripts/check-secrets.sh'

check_pattern \
  'REPLACE_TURN_SECRET|REPLACE_DOMAIN' \
  'an unsubstituted coturn placeholder outside its source template' \
  'turnserver.conf' 'scripts/check-secrets.sh' 'scripts/coturn-entrypoint.sh' '.planning/' '.env.example' \
  'docs/deployment/ops-runbook.md'

check_pattern \
  '\bsk-[A-Za-z0-9_-]{20,}\b' \
  'an OpenAI-style secret key (sk-...)' \
  'scripts/check-secrets.sh'

check_pattern \
  '\bGOCSPX-[A-Za-z0-9_-]{20,}\b' \
  'a Google OAuth client secret (GOCSPX-...)' \
  'scripts/check-secrets.sh'

if [ "$fail" -ne 0 ]; then
  echo "check-secrets.sh: one or more checks failed. See above." >&2
  exit 1
fi

echo "check-secrets.sh: no known-bad secrets found in tracked files."
