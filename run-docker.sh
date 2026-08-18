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
PORT="${PORT:-5002}"

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
