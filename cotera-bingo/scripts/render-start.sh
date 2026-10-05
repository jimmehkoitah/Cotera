#!/usr/bin/env bash
# Runs the built Worker on Render with Cloudflare's runtime (workerd, via Miniflare) and
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

$WRANGLER d1 execute DB --local --persist-to "$STATE" --config "$CONFIG" --file scripts/render-schema.sql

# Not `wrangler dev`: its DevTools proxy buffers every request's inspector events in memory.
export STATE_DIR="$STATE" PUBLIC_HOSTNAME="$PUBLIC_HOST"
exec node scripts/render-serve.mjs
