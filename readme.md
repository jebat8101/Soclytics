<div align="center">

<img src="app/icons/logo.png" alt="Soclytics Logo" width="300"/>

# Soclytics

### *Beyond The Metrics — No LLM Edition*

[![Python](https://img.shields.io/badge/Python-3.12-blue?style=flat-square&logo=python)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-Web%20UI-black?style=flat-square&logo=flask)](https://flask.palletsprojects.com)
[![SeleniumBase](https://img.shields.io/badge/SeleniumBase-Undetected%20Chrome-green?style=flat-square)](https://github.com/seleniumbase/SeleniumBase)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)]()
[![LLM](https://img.shields.io/badge/LLM%20Required-None-brightgreen?style=flat-square)]()

**Local-first multi-platform SOCMINT — Facebook, Instagram, Reddit, Threads, and Telegram. No LLM, no cloud dependency. Docker is the recommended install. For the AI-powered version see [birdy-edwards](https://github.com/jeet-ganguly/birdy-edwards).**

[Installation](#installation-docker) · [Platforms](#platforms--mini-apps) · [Features](#features) · [Troubleshooting](#troubleshooting) · [Disclaimer](#️-disclaimer) · [Contributing](#contributing)

</div>

---

## What is Soclytics?

Soclytics is a local-first, dependency-light multi-platform SOCMINT platform. It runs four separate mini-apps — **Facebook**, **Instagram**, **Reddit**, and **Threads** — each with its own cookies, database, and investigation history.

Each platform performs the same core workflow — data gathering, interaction mapping, network visualization, and (where applicable) face clustering — without requiring any AI model or cloud service.

Everything runs on your local machine. No GPU required. No model downloads. No official platform APIs.

<img src="app/icons/demo.png" alt="Soclytics Web UI" width="100%"/>


---

## Architecture

<div align="center">
<img src="app/icons/workflow-lite.png" alt="Soclytics Pipeline" width="100%"/>
</div>

Shared shell tabs switch between mini-apps:

| Tab | URL | Cookie file | Database |
|---|---|---|---|
| Facebook | `/facebook` | `fb_cookies.pkl` | `socmint_fb.db` |
| Instagram | `/instagram` | `ig_cookies.pkl` | `socmint_ig.db` |
| Reddit | `/reddit` | `reddit_cookies.pkl` | `socmint_reddit.db` |
| Threads | `/threads` | `threads_cookies.pkl` | `socmint_threads.db` |

`/` redirects to `/facebook` for backward compatibility.

---

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

## Features

- 🔍 **Profile data gathering** — Automated collection of posts/submissions, photos/reels (FB/IG), about data, comments, interactor names and profile links
- 📊 **Like / Comment / Repost counts** — All platforms store Like, Comment, and Repost by parsing the post page (X.com pattern); named likers/sharers are not collected
- 📈 **Engagement dashboards** — Home sums, post metrics, and Activity Timeline (stacked Like / Comment / Repost); **Views stay X-only**
- 📊 **Frequency scoring** — Weighted interaction frequency ranking across gathered content
- 🕸️ **Network graph** — Interactive force-directed graph showing target ↔ interactor relationships, frequency-weighted edges, fullscreen mode
- 🔗 **Co-interactor matrix** — Heatmap showing which interactors appeared together across posts, with threshold filtering (1+, 2+, 3+, 5+)
- 💠 **Co-interactor force graph** — Force-directed cluster view of interactor co-occurrence relationships, fullscreen mode
- 📈 **Interaction timeline** — Date-wise stacked bar chart of interactions
- 🍩 **Distribution donut** — Breakdown of interactions by media / content type
- 👤 **Face intelligence** — CNN / HOG face detection and clustering (**Facebook + Instagram + Threads**; Reddit omits this step)
- 🌳 **Face cluster tree** — Frequency-cascade hierarchy of detected persons (FB/IG)
- 🎯 **Top 7 priority targets** — Highest-frequency interactors with about-data cards where available
- 📋 **About data cards** — Target and Top 7 interactor profile fields
- 🗑️ **Investigation management** — Delete any investigation and its gathered data from the home page
- 🌙 **Dark / light theme** — Full theme toggle across all dashboard components
- 🤖 **Zero LLM dependency** — No Ollama, no model download, no GPU needed

---

## ⚠️ Disclaimer

> Soclytics is developed strictly for **authorized intelligence, law enforcement, and academic research purposes only.**
>
> **Scope of data access:**
> - This tool operates exclusively using a valid platform session authenticated by the operator (Facebook, Instagram, Reddit, or Threads cookies)
> - It only accesses **publicly visible** profile data, posts/submissions, media, and comments
> - It does **not** access private messages, locked profiles, restricted content, or any data not visible to a logged-in user
> - It does **not** use bots, fake accounts, or automated account creation — the operator supplies their own authenticated session
> - It does **not** call official platform APIs
>
> **Legal responsibility:**
> - This tool must only be used on profiles and content where you have **explicit legal authorization** to collect and analyze data
> - Use without authorization may violate platform Terms of Service, applicable privacy laws (GDPR, IT Act, DPDP Act), and local regulations
> - The developer assumes **no liability** for misuse, unauthorized data collection, or any harm caused by improper use
> - All investigations are the **sole responsibility of the operator**
>
> By using Soclytics, you confirm that your use is lawful, authorized, and compliant with all applicable laws in your jurisdiction.

---

## Comparison — Lite vs Full

| Capability | Lite | Full (AI) |
|---|:---:|:---:|
| Profile data gathering | ✅ | ✅ |
| Facebook / Instagram / Reddit / Threads / Telegram | ✅ | — |

| Interaction frequency scoring | ✅ | ✅ |
| Network + co-interactor graphs | ✅ | ✅ |
| Timeline + donut charts | ✅ | ✅ |
| CNN / HOG face clustering (FB/IG) | ✅ | ✅ |
| Top 7 metadata gathering | ✅ | ✅ |
| AI sentiment / emotion analysis | ❌ | ✅ |
| Actor composite scoring | ❌ | ✅ |
| Country of origin detection | ❌ | ✅ |
| World map visualization | ❌ | ✅ |
| PDF intelligence report | ✅ | ✅ |
| JSON report export | ✅ | ✅ |
| Docker deployment | ✅ | ✅ |
| LLM required | ❌ None | ✅ Ollama |
| GPU required | ❌ | ✅ Recommended |

---

## System Requirements

| Component | Minimum | Recommended |
|---|---|---|
| OS | Ubuntu 22.04+ | Ubuntu 24.04 LTS |
| Python | 3.10+ | 3.12 |
| RAM | 4 GB | 8 GB |
| Storage | 5 GB free | 10 GB free |
| Browser | Chrome / Chromium | Latest Chrome |

> Windows users must use WSL.

---

## Installation (Docker)

Recommended. Host port **5002**. First build compiles dlib and takes several minutes.

### Step 1 — Clone the repository

```bash
git clone http://gitlab.eclab.net/osint/birdy-edwards-lite-v2.git
cd birdy-edwards-lite-v2
```

### Step 2 — Configure

```bash
cp .env.example .env
```

`.env` already sets `PORT=5002`. Optional Telegram MTProto keys (`TG_API_ID`, `TG_API_HASH` from https://my.telegram.org). Public channel preview works without them.

### Step 3 — Start the container

```bash
chmod +x run-docker.sh
./run-docker.sh
```

Creates cookie/db placeholders, then `docker compose up --build -d`. Re-run anytime to rebuild/restart.

```bash
docker compose logs -f       # follow logs
docker compose down          # stop
./run-docker.sh --update     # git pull + rebuild
```

### Step 4 — Open the web UI

```
http://localhost:5002          → redirects to /facebook
http://localhost:5002/facebook
http://localhost:5002/instagram
http://localhost:5002/reddit
http://localhost:5002/threads
http://localhost:5002/telegram
http://localhost:5002/x
```

## Installation (local venv)

Use this if you cannot run Docker.

### Step 1 — Clone the repository

```bash
git clone http://gitlab.eclab.net/osint/birdy-edwards-lite-v2.git
cd birdy-edwards-lite-v2
```

### Step 2 — Run the setup script

```bash
chmod +x setup.sh
./setup.sh
```

The setup script will:
- Check your Python version (3.10+ required)
- Install system build dependencies (cmake, build-essential, etc.)
- Create a Python virtual environment
- Compile and install dlib (5–10 minutes)
- Install face_recognition and models
- Install Flask, SeleniumBase, Pillow, NumPy
- Install Chrome driver
- Patch face_recognition_models for Python 3.12 compatibility
- Create required directories

> ⚠️ dlib compiles from source. This takes 5–10 minutes on first run. Do not interrupt it.

### Step 3 — Start the app

```bash
source venv/bin/activate
cd app
python3 app.py
```

### Step 4 — Open the web UI

```
http://localhost:5000          → redirects to /facebook
http://localhost:5000/facebook
http://localhost:5000/instagram
http://localhost:5000/reddit
http://localhost:5000/threads
http://localhost:5000/telegram
```
---

## Session Setup (cookies)

Soclytics uses the **Cookie-Editor** browser extension. Each mini-app has its own cookie file — import cookies while logged into that platform.

> 🔒 **Operational Security:** Use a dedicated investigation account rather than your personal account.

1. Install Cookie-Editor:
   - [Chrome](https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmd)
   - [Firefox](https://addons.mozilla.org/en-US/firefox/addon/cookie-editor/)
2. Log into your dedicated investigation account on the target platform
3. Click Cookie-Editor while on `facebook.com`, `instagram.com`, or `reddit.com`
4. Click **Export → Export as JSON**
5. Open the matching tab in the UI (`/facebook`, `/instagram`, or `/reddit`)
6. Paste into **IMPORT COOKIES** and click **SAVE COOKIES**

| Platform | Cookie file | Required cookie names (examples) |
|---|---|---|
| Facebook | `fb_cookies.pkl` | `c_user`, `xs` |
| Instagram | `ig_cookies.pkl` | `sessionid` |
| Reddit | `reddit_cookies.pkl` | `reddit_session` or `token_v2` |
| Threads | `threads_cookies.pkl` | `sessionid` (from threads.com) |

> Cookies expire periodically. Re-import fresh cookies if the pipeline fails at the data gathering stage.

---

## Telegram Setup

Telegram does **not** use browser cookies — it uses MTProto (Telethon) with an optional public-preview fallback.

| Mode | Requirements | What you get |
|---|---|---|
| **MTProto** (recommended) | `telethon` + `TG_API_ID` / `TG_API_HASH` + authorized session | Posts, media, discussion comments, reactors, forwards, mentions, admins |
| **Public preview** | Nothing | Posts/media/views from `t.me/s/<name>` — no commenters |

```bash
# 1. Get api_id + api_hash from https://my.telegram.org
# 2. Authorize once (interactive phone + code):
source venv/bin/activate
python3 scripts/telegram-login.py

# Or via env vars:
export TG_API_ID=12345
export TG_API_HASH=abcdef...
python3 scripts/telegram-login.py
```

Then open **http://localhost:5002/telegram** (Docker) or **http://localhost:5000/telegram** (local venv), paste `t.me/channel` or `@name`, pick depth, and **LAUNCH**.

---

## Running an Investigation

1. Open the platform tab (`/facebook`, `/instagram`, `/reddit`, `/threads`, or `/telegram`)
2. Verify the cookie / session status bar (Telegram: public preview always works)
3. Enter a **profile-only** target URL
4. Select scan depth (Light / Medium / Deep)
5. Click **LAUNCH PIPELINE** / **START INVESTIGATION**
6. The pipeline overlay shows live progress (Reddit omits the face step)
7. On completion you are redirected to that platform’s analysis dashboard

---

## Analysis Dashboard

The dashboard renders gathered intelligence without server-side AI processing.

| Section | What it shows |
|---|---|
| **Interactor Registry** | All interactors ranked by total interaction count |
| **Apex Interactor** | The single most frequent interactor with full stats |
| **Interaction Distribution** | Donut chart by content type |
| **Timeline** | Date-wise stacked bar chart of interactions |
| **Top 7 Priority Targets** | Top 7 interactors with about-data VIEW button |
| **Network Graph** | Force-directed target ↔ interactor graph |
| **Co-Interactor Matrix** | Heatmap of who appeared together |
| **Co-Interactor Force Graph** | Cluster view of co-occurrence |
| **Face Cluster Tree** | Frequency-cascade tree (**Facebook + Instagram only**) |

Clicking any node or interactor row opens a side panel with interaction samples and profile link.

### Download report (PDF / JSON)

From any analysis dashboard top bar:

| Button | Endpoint | Contents |
|---|---|---|
| **↓ PDF** | `/{platform}/reports/pdf/<id>` | Full SOCMINT PDF (summary, network, interactors, Top-7, posts, comments, timeline, faces) |
| **↓ JSON** | `/{platform}/reports/json/<id>` | Same dataset as machine-readable JSON |

Files are written under `app/reports/` and downloaded by the browser. Requires `reportlab` and `matplotlib` (installed by `setup.sh`).

---

## How You Can Help

If you find Soclytics useful or interesting, here are a few ways you can support the project:

- ⭐ **Star the repository** — it helps others discover the tool
- 🐛 **Report bugs** — open an Issue if something isn't working
- 🔧 **Contribute** — check the [Contributing](#contributing) section to get started
- 📢 **Share it** — post it in OSINT communities, forums, X or with colleagues who might find it useful
- 💬 **Give feedback** — suggestions for new features or improvements are always welcome

Every contribution, big or small, helps build better tools for the OSINT and threat intelligence community.

---

## Troubleshooting

**dlib compilation fails**
Make sure cmake and build-essential are installed. Run `sudo apt install cmake build-essential` then retry `pip install dlib`.

**face_recognition crashes or errors on Python 3.12**
The setup script patches `face_recognition_models` automatically. If you installed manually, run:
```bash
source venv/bin/activate
python3 -c "
import sys, os
path = os.path.join(sys.prefix, 'lib', f'python{sys.version_info.major}.{sys.version_info.minor}', 'site-packages')
print(path)
"
```
Then check that `face_recognition_models/__init__.py` does not reference `pkg_resources`.

**Pipeline fails at data gathering stage**
Your cookies have likely expired. Re-export from Cookie-Editor on the correct domain and re-import in the matching mini-app tab.

**No faces detected (Facebook / Instagram)**
CDN URLs expire. Face clustering only works immediately after a fresh pipeline run while image URLs are still valid. Reddit has no face step.

**Port 5000 already in use (local venv)**
Set `PORT=5001` or edit `app.py` to use another port, then access at `http://localhost:5001`.

**Docker host port already in use**
Change `PORT` in `.env` (default `5002`) and re-run `./run-docker.sh`.

**DB error: no such table**
Delete the investigation from the home page and start a new one. The schema is created automatically on first use. Databases are `socmint_fb.db`, `socmint_ig.db`, and `socmint_reddit.db`.

---

## Contributing

Contributions are welcome. Please follow these guidelines.

**Reporting bugs** — Open an Issue with steps to reproduce, OS, Python version, and relevant terminal output.

**Feature requests** — Open an Issue describing the feature and its investigative use case before opening a Pull Request.

**Submitting a Pull Request:**
```bash
git checkout -b feature/your-feature-name
git commit -m "Add: short description"
git push origin feature/your-feature-name
```
Then open a Pull Request against `main`.

**Code guidelines:**
- Python 3.12, Flask conventions
- Test locally before submitting
- Do not commit `fb_cookies.pkl`, `ig_cookies.pkl`, `reddit_cookies.pkl`, `threads_cookies.pkl`, databases, or any gathered data
- Keep gatherer changes minimal — platform DOMs change frequently

**What we welcome:** bug fixes, UI improvements, new chart types, dashboard features, documentation improvements, stability improvements.

**What we do not accept:** features that introduce cloud dependencies, changes that store or transmit gathered data externally, features that bypass platform security controls.

---

## Acknowledgements

- Inspired by [Sherlock](https://github.com/sherlock-project/sherlock) and the OSINT research community
- [SeleniumBase](https://github.com/seleniumbase/SeleniumBase) — Undetected Chrome automation
- [face_recognition](https://github.com/ageitgey/face_recognition) — Face detection and 128D encoding
- [D3.js](https://d3js.org) — Network and force-directed graph rendering
- [Chart.js](https://www.chartjs.org) — Timeline, donut, and bar chart rendering
- [Flask](https://flask.palletsprojects.com) — Web framework

---

<div align="center">

**Soclytics** · Beyond The Metrics · No LLM · Local-First · Facebook · Instagram · Reddit · Threads · Telegram

</div>
