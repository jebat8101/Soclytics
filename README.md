# Soclytics (Birdy-Edwards Lite v2)

Local-first multi-platform SOCMINT — Facebook, Instagram, Reddit, Threads, Telegram. No LLM required.

**Recommended install: Docker** (host port **5002**). First build compiles dlib and takes several minutes.

## Prerequisites

- Linux (Ubuntu 22.04+ recommended)
- Docker Engine + Docker Compose plugin
- Git

## 1. Clone

```bash
git clone http://gitlab.eclab.net/osint/birdy-edwards-lite-v2.git
cd birdy-edwards-lite-v2
```

## 2. Configure

```bash
cp .env.example .env
```

`.env` already sets `PORT=5002`. Optional Telegram MTProto (full comments / reactors):

```bash
# Get keys from https://my.telegram.org
TG_API_ID=12345
TG_API_HASH=your_hash_here
```

Without those vars, Telegram still works in **public preview** (`t.me/s/...` posts/media, no commenters).

## 3. Start the container

```bash
chmod +x run-docker.sh
./run-docker.sh
```

This creates cookie/db placeholder files, then runs `docker compose up --build -d`. Re-run anytime to rebuild/restart.

## 4. Open the UI

```
http://localhost:5002              → redirects to /facebook
http://localhost:5002/facebook
http://localhost:5002/instagram
http://localhost:5002/reddit
http://localhost:5002/threads
http://localhost:5002/telegram
http://localhost:5002/x
```

## 5. Import cookies (Facebook / Instagram / Reddit / Threads / X)

Telegram does **not** use cookies.

1. Install Cookie-Editor ([Chrome](https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmd) / [Firefox](https://addons.mozilla.org/en-US/firefox/addon/cookie-editor/))
2. Log in to the platform in your browser
3. Export → Export as JSON
4. Paste into **IMPORT COOKIES** on the matching tab and save

Use a dedicated investigation account, not a personal account.

## Stop / logs / update

```bash
docker compose logs -f          # follow logs
docker compose down             # stop
./run-docker.sh --update        # git pull + rebuild
```

## Optional — Telegram MTProto login (once)

```bash
# After TG_API_ID / TG_API_HASH are in .env (or passed as flags):
python3 scripts/telegram-login.py
./run-docker.sh
```

This writes `app/telegram.session` and `app/telegram_config.json`, which docker-compose mounts into the container.

## Native (no Docker)

See [readme.md](readme.md#installation-local-venv) for `./setup.sh` and `python3 app.py`.
