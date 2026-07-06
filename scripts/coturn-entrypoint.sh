#!/bin/sh
# Generates /etc/coturn/turnserver.conf from the tracked turnserver.conf
# template by substituting TURN_SECRET / TURN_REALM env vars, then execs
# turnserver. Refuses to start if either env var is missing or still set to
# the tracked placeholder value — this is the only thing standing between a
# fresh checkout and a coturn instance running with a public placeholder
# secret.
set -eu

: "${TURN_SECRET:?TURN_SECRET must be set (see .env.example)}"
: "${TURN_REALM:?TURN_REALM must be set (see .env.example)}"

if [ "$TURN_SECRET" = "REPLACE_TURN_SECRET" ]; then
  echo "coturn-entrypoint: TURN_SECRET is still the placeholder value REPLACE_TURN_SECRET. Refusing to start." >&2
  exit 1
fi

if [ "$TURN_REALM" = "REPLACE_DOMAIN" ]; then
  echo "coturn-entrypoint: TURN_REALM is still the placeholder value REPLACE_DOMAIN. Refusing to start." >&2
  exit 1
fi

sed -e "s#REPLACE_TURN_SECRET#${TURN_SECRET}#" \
    -e "s#REPLACE_DOMAIN#${TURN_REALM}#" \
    /templates/turnserver.conf > /etc/coturn/turnserver.conf

exec turnserver -c /etc/coturn/turnserver.conf -n
