#!/usr/bin/env python3
"""
Create a Telegram session dedicated to the container.

Telethon needs an interactive phone + code exchange once. The web UI never
prompts, so run this from a terminal before starting the container:

    source venv/bin/activate
    python3 scripts/telegram-login.py

Writes app/telegram.session and app/telegram_config.json — both are mounted
into the container by docker-compose, so no environment variables are needed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
DEFAULT_SESSION = os.path.join(APP_DIR, "telegram")
DEFAULT_CONFIG = os.path.join(APP_DIR, "telegram_config.json")

sys.path.insert(0, APP_DIR)


def existing_credentials() -> tuple[str | None, str | None]:
    """Reuse api_id / api_hash already configured on this machine, if any."""
    try:
        from platforms.telegram.collector import load_config
    except Exception:
        return None, None
    cfg = load_config()
    if not cfg:
        return None, None
    print(f"Found credentials in {cfg['source']}")
    return str(cfg["api_id"]), cfg["api_hash"]


def main() -> int:
    ap = argparse.ArgumentParser(description="Authorize a Telegram session for the container")
    ap.add_argument("--api-id", help="api_id from my.telegram.org")
    ap.add_argument("--api-hash", help="api_hash from my.telegram.org")
    ap.add_argument("--session", default=DEFAULT_SESSION,
                    help="session path without the .session extension")
    ap.add_argument("--config", default=DEFAULT_CONFIG, help="config file to write")
    args = ap.parse_args()

    try:
        from telethon.sync import TelegramClient
    except ImportError:
        print("telethon is not installed — run: pip install telethon", file=sys.stderr)
        return 1

    api_id, api_hash = args.api_id, args.api_hash
    if not (api_id and api_hash):
        found_id, found_hash = existing_credentials()
        api_id = api_id or found_id
        api_hash = api_hash or found_hash
    if not api_id:
        api_id = input("api_id: ").strip()
    if not api_hash:
        api_hash = input("api_hash: ").strip()

    try:
        api_id = int(api_id)
    except ValueError:
        print(f"api_id must be numeric, got {api_id!r}", file=sys.stderr)
        return 1

    session_path = os.path.abspath(args.session)
    if session_path.endswith(".session"):
        session_path = session_path[: -len(".session")]
    os.makedirs(os.path.dirname(session_path), exist_ok=True)

    # An empty placeholder from stack-prepare.sh is not a valid SQLite session
    placeholder = session_path + ".session"
    if os.path.exists(placeholder) and os.path.getsize(placeholder) == 0:
        os.remove(placeholder)

    print(f"\nAuthorizing {placeholder}")
    print("Telegram will send a login code to your account.\n")

    client = TelegramClient(session_path, api_id, api_hash)
    client.start()
    try:
        me = client.get_me()
        handle = f"@{me.username}" if me.username else f"id {me.id}"
        name = " ".join(p for p in (me.first_name, me.last_name) if p)
        print(f"\nAuthorized as {name} ({handle})")
    finally:
        client.disconnect()

    with open(args.config, "w", encoding="utf-8") as f:
        json.dump({
            "api_id": api_id,
            "api_hash": api_hash,
            "session_name": os.path.basename(session_path),
        }, f, indent=2)
    os.chmod(args.config, 0o600)

    print(f"Session  → {placeholder}")
    print(f"Config   → {args.config}")
    print("\nBoth are mounted into the container. Start it with:")
    print("  ./run-docker.sh")
    return 0


if __name__ == "__main__":
    sys.exit(main())
