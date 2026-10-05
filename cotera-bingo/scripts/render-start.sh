#!/usr/bin/env bash
# Runs the built Worker on Render with Cloudflare's local runtime (workerd) and
# a SQLite-backed D1 database, so the game code and storage stay unchanged.
# Build first with: npm ci && npm run build
set -euo pipefail
cd "$(dirname "$0")/.."

: "${ADMIN_PIN:?ADMIN_PIN must be set}"
: "${ADMIN_SECRET:?ADMIN_SECRET must be set}"

# Keep the database on Render's persistent disk when one is mounted.
DATA_DIR="${DATA_DIR:-/var/data}"
if mkdir -p "$DATA_DIR/wrangler-state" 2>/dev/null && [ -w "$DATA_DIR/wrangler-state" ]; then
  STATE="$DATA_DIR/wrangler-state"
else
  STATE="$PWD/.wrangler/state"
  echo "WARNING: $DATA_DIR is not writable; using $STATE, which is lost on restart." >&2
fi
mkdir -p "$STATE"
echo "Database directory: $STATE"

# The API compares the browser Origin with the request URL, so the Worker must
# see the public HTTPS hostname rather than the internal listener address.
PUBLIC_HOST="${PUBLIC_HOSTNAME:-${RENDER_EXTERNAL_HOSTNAME:-}}"
if [ -z "$PUBLIC_HOST" ]; then
  echo "PUBLIC_HOSTNAME or RENDER_EXTERNAL_HOSTNAME must be set." >&2
  exit 1
fi

export CLOUDFLARE_CF_FETCH_ENABLED=false WRANGLER_SEND_METRICS=false
WRANGLER="node node_modules/wrangler/bin/wrangler.js"
CONFIG=dist/server/wrangler.json

# Secrets reach the Worker through .dev.vars next to the generated config.
umask 077
printf 'ADMIN_PIN=%s\nADMIN_SECRET=%s\n' "$ADMIN_PIN" "$ADMIN_SECRET" > dist/server/.dev.vars

$WRANGLER d1 execute DB --local --persist-to "$STATE" --config "$CONFIG" --file scripts/render-schema.sql

exec $WRANGLER dev --config "$CONFIG" --local --persist-to "$STATE" \
  --ip 0.0.0.0 --port "${PORT:-10000}" --inspector-port 0 \
  --show-interactive-dev-session=false --log-level warn \
  --local-upstream "$PUBLIC_HOST" --upstream-protocol https
