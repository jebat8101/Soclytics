What is Soclytics?

Soclytics is a local-first, dependency-light multi-platform SOCMINT platform. It runs six separate mini-apps — Facebook, Instagram, Reddit, Threads, Telegram, and X — each with its own cookies, database, and investigation history.

Each platform performs the same core workflow — data gathering, interaction mapping, network visualization, and (where applicable) face clustering — without requiring any AI model, Docker container, or cloud service.

Everything runs on your local machine. No GPU required. No model downloads. No official platform APIs..

**Recommended install: Docker** (host port **5002**). First build compiles dlib and takes several minutes.

## Platforms · Mini-Apps

### Targets (profile-only)

| Platform | Accepted targets | Rejected |
|---|---|---|
| Facebook | Profile URL | — |
| Instagram | `https://www.instagram.com/<user>/`, `@user`, or bare `user` | Stories, hashtags, locations |
| Reddit | `https://www.reddit.com/user/<name>/` or `u/<name>` | Subreddits, search queries |
| Threads | `https://www.threads.com/@<user>/`, `@user`, or bare `user` | Individual post URLs, search |

### Per-platform gather

- **Facebook** — about, photos, reels, text posts + comments; Like / Comment / Repost from post footer (**Share → Repost**); face clustering
- **Instagram** — about, posts, reels + comments; Like / Comment / Repost from post page (Repost 0 unless visible); face clustering
- **Reddit** — about, submissions + comments on those submissions; **score → Like**, Comment count, Repost 0; **no** face step
- **Threads** — about, posts/threads + Like / Comment / Repost from displayed counts; face clustering on image posts
- **Telegram** — posts/media + comments; **reactions → Like**, **forwards → Repost**; MTProto or public preview
- **X** — posts + replies; Like / Comment / Repost from post page; **Views (X-only)**

Auth is operator cookies + SeleniumBase only (no Graph API / no `praw`).

---

## Prerequisites

- Linux (Ubuntu 22.04+ recommended)
- Docker Engine + Docker Compose plugin
- Git

## 1. Clone

```bash
git clone https://github.com/jebat8101/Soclytics.git
cd Soclytics
```

## 2. Configure

```bash
cp .env.example .env
```

`.env` already sets `PORT=5002`. Optional Telegram MTProto (full comments / reactors):

```bash
python3 scripts/telegram-login.py
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
