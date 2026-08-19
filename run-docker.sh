#!/bin/bash
# One-time setup + start (or re-run anytime to rebuild/restart).
# Usage:
#   ./run-docker.sh           start / restart container
#   ./run-docker.sh --update  git pull, then rebuild and start

set -euo pipefail
cd "$(dirname "$0")"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

port_explicitly_set=0
if [[ -n "${PORT:-}" ]]; then
  port_explicitly_set=1
fi

PORT="${PORT:-5002}"

port_in_use() {
  python3 - "$1" <<'PY'
import socket
import sys

port = int(sys.argv[1])
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("0.0.0.0", port))
    except OSError:
        raise SystemExit(0)
    raise SystemExit(1)
PY
}

compose_host_port() {
  docker compose port birdy-edwards-lite 5000 2>/dev/null | python3 -c '
import sys

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    print(line.rsplit(":", 1)[-1])
    break
'
}

if (( port_explicitly_set )); then
  existing_compose_port="$(compose_host_port || true)"
  if [[ "${existing_compose_port}" != "${PORT}" ]] && port_in_use "$PORT"; then
    echo "Configured host port ${PORT} is already in use. Set a free PORT in .env or run with PORT=<port> ./run-docker.sh"
    exit 1
  fi
else
  while port_in_use "$PORT"; do
    PORT="$((PORT + 1))"
  done
fi

export PORT

if [[ "${1:-}" == "--update" ]]; then
  echo "Pulling latest from origin..."
  git pull origin main
fi

echo "Preparing data directories and mount files..."
mkdir -p \
  app/face_data app/face_data_ig app/face_data_threads app/face_data_tg \
  app/post_screenshots app/telegram_media app/reports app/icons

for f in \
  app/fb_cookies.pkl app/ig_cookies.pkl app/reddit_cookies.pkl app/threads_cookies.pkl \
  app/socmint_fb.db app/socmint_ig.db app/socmint_reddit.db app/socmint_threads.db app/socmint_tg.db \
  app/telegram_config.json app/telegram.session
do
  touch "$f"
done

echo "Building and starting Docker (host port ${PORT})..."
docker compose up --build -d

echo ""
echo "Birdy-Edwards Lite is running:"
echo "  http://localhost:${PORT}"
echo ""
echo "Useful commands:"
echo "  docker compose logs -f     follow logs"
echo "  docker compose down        stop container"
echo "  ./run-docker.sh --update   pull + rebuild"
