#!/bin/bash
set -e

RED='\033[0;31m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RESET='\033[0m'

echo ""
echo -e "${YELLOW}Birdy-Edwards Lite (Docker)${RESET}"
echo -e "${CYAN}Facebook · Instagram · Reddit · Threads${RESET}"
echo ""

echo "[1/3] Starting Xvfb..."
Xvfb :99 -screen 0 1280x900x24 -nolisten tcp &
sleep 2

echo "[2/3] Runtime dirs..."
mkdir -p /app/face_data /app/face_data_ig /app/face_data_threads /app/post_screenshots /app/icons

echo "[3/3] Starting Flask on 0.0.0.0:${PORT:-5000}"
cd /app
exec python3 app.py
