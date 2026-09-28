#!/usr/bin/env bash
# Bring the Burk.pk SCM-OVS stack up locally.
#
#   ./run-local.sh          start everything (SQLite, no Docker needed)
#   ./run-local.sh stop     stop everything
#
# By default this runs on a local SQLite file so no Docker/Postgres is
# required. To use the project's real Postgres instead, start the container
# first and export the URL before running this script:
#
#   sudo docker compose up -d
#   export DATABASE_URL="postgres://burk:burk@localhost:5433/burk_scm"
#   ./run-local.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGDIR="$ROOT/.local-logs"
export PATH="$HOME/.local/bin:$PATH"
export DATABASE_URL="${DATABASE_URL:-sqlite:///$ROOT/local-dev.sqlite3}"

BACKEND_PORT=8000
FRONTEND_PORT=3001   # must be 3001: CSRF_TRUSTED_ORIGINS only trusts this port

# `|| true` matters: under `set -euo pipefail` a no-match grep would
# otherwise abort the script the moment a port is already free.
port_pid() {
  ss -ltnp 2>/dev/null | grep ":$1 " | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2 || true
}

stop_port() {
  local pid; pid="$(port_pid "$1" || true)"
  if [ -n "$pid" ]; then echo "  stopping pid $pid on port $1"; kill "$pid" 2>/dev/null || true; fi
}

# Explicit-PID kills only. pkill/fuser -k have been observed killing the
# calling shell on this machine.
stop_worker() {
  local pids; pids="$(pgrep -f "manage.py run_worker --worker-name local-dev" || true)"
  for pid in $pids; do
    [ "$pid" = "$$" ] && continue
    echo "  stopping worker pid $pid"; kill "$pid" 2>/dev/null || true
  done
}

if [ "${1:-start}" = "stop" ]; then
  echo "Stopping Burk.pk SCM-OVS..."
  stop_port "$FRONTEND_PORT"; stop_port "$BACKEND_PORT"; stop_worker
  echo "Stopped."
  exit 0
fi

mkdir -p "$LOGDIR"

echo "==> Database: $DATABASE_URL"
cd "$ROOT/backend"
uv sync --quiet
uv run python manage.py migrate --noinput >"$LOGDIR/migrate.log" 2>&1
if ! uv run python manage.py shell -c \
     "import sys;from inventory.models import Product;sys.exit(0 if Product.objects.exists() else 1)" \
     >/dev/null 2>&1; then
  echo "==> Seeding demo data"
  uv run python manage.py seed_demo
fi

echo "==> Backend  http://127.0.0.1:$BACKEND_PORT"
stop_port "$BACKEND_PORT"
setsid nohup env DATABASE_URL="$DATABASE_URL" PATH="$PATH" \
  uv run python manage.py runserver "127.0.0.1:$BACKEND_PORT" --noreload \
  >"$LOGDIR/backend.log" 2>&1 </dev/null &

echo "==> Worker (durable job queue)"
stop_worker
setsid nohup env DATABASE_URL="$DATABASE_URL" PATH="$PATH" \
  uv run python manage.py run_worker --worker-name local-dev --poll-interval 2 \
  >"$LOGDIR/worker.log" 2>&1 </dev/null &

for _ in $(seq 1 30); do ss -ltn 2>/dev/null | grep -q ":$BACKEND_PORT " && break; sleep 1; done

echo "==> Building frontend"
cd "$ROOT/frontend"
npm run build >"$LOGDIR/build.log" 2>&1 || { echo "frontend build failed — see $LOGDIR/build.log"; exit 1; }

echo "==> Frontend http://localhost:$FRONTEND_PORT"
stop_port "$FRONTEND_PORT"
setsid nohup npx next start -p "$FRONTEND_PORT" >"$LOGDIR/frontend.log" 2>&1 </dev/null &
for _ in $(seq 1 40); do ss -ltn 2>/dev/null | grep -q ":$FRONTEND_PORT " && break; sleep 1; done

sleep 2
echo
echo "Health: $(curl -s "http://localhost:$FRONTEND_PORT/api/health/")"
echo
echo "  Open   http://localhost:$FRONTEND_PORT"
echo "  Login  manager / burkdemo123   (or operator / burkdemo123)"
echo "  Logs   $LOGDIR"
echo "  Stop   ./run-local.sh stop"
