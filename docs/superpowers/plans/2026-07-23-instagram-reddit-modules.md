# Instagram & Reddit Modules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor Birdy-Edwards Lite into platform packages + shared core, then add Instagram and Reddit mini-apps with full Facebook-parity gather → DB → frequency → graphs (faces on FB/IG only).

**Architecture:** Thin Flask `app.py` registers three blueprints (`/facebook`, `/instagram`, `/reddit`). Shared `core/` owns browser/cookie helpers, pipeline step state, scoring, face clustering, and DB helpers. Each `platforms/<name>/` owns scrapers, platform DB/import, routes, and templates. Spec: `docs/superpowers/specs/2026-07-23-instagram-reddit-modules-design.md`.

**Tech Stack:** Python 3.10+, Flask blueprints, SeleniumBase (undetected Chrome), SQLite, Pillow/NumPy/face_recognition (IG+FB faces), pytest.

## Global Constraints

- Auth: operator cookies + SeleniumBase only (no Instagram Graph API, no Reddit `praw` in v1)
- Targets: profile/user only (IG username/URL; Reddit `/user/<name>`)
- Separate mini-apps: own cookie file, own DB, own investigation history per platform
- DB files: `socmint_fb.db`, `socmint_ig.db`, `socmint_reddit.db`
- Cookie files: `fb_cookies.pkl`, `ig_cookies.pkl`, `reddit_cookies.pkl`
- `/` redirects to `/facebook`; existing FB behavior must keep working after refactor
- Reddit pipeline omits face clustering; Instagram includes posts + reels (no Stories)
- Lite remains zero-LLM
- Run app and tests with cwd = `app/` (or set `PYTHONPATH=app`) so `core` / `platforms` imports resolve
- Authorized-use disclaimer unchanged; scrape only what the operator session can already see

---

## File Structure (target)

```
app/
  app.py                          # create Flask app, register blueprints, `/` → facebook
  core/
    __init__.py
    browser.py                    # cookie pickle helpers
    pipeline.py                   # PipelineState / reset / set_step
    scoring.py                    # moved from commentor_scoring_lite.py
    face.py                       # moved from face_intelligence_lite.py
    db_base.py                    # migrate_legacy_fb_db, connect
    urls.py                       # normalize_instagram_target, normalize_reddit_target
  platforms/
    __init__.py
    facebook/
      __init__.py
      blueprint.py
      db.py
      about_sb.py, photos_sb.py, reels_sb.py, posts_sb.py
      constants.py
    instagram/
      __init__.py
      blueprint.py
      db.py
      constants.py
      about_sb.py, posts_sb.py, reels_sb.py
    reddit/
      __init__.py
      blueprint.py
      db.py
      constants.py
      about_sb.py, submissions_sb.py
  templates/
    _shell.html
    facebook/index.html, analysis.html
    instagram/index.html, analysis.html
    reddit/index.html, analysis.html
  tests/
    test_pipeline.py
    test_urls.py
    test_db_migrate.py
    test_ig_db_import.py
    test_reddit_db_import.py
    fixtures/
      ig_about.json, ig_posts.json, ig_reels.json
      reddit_about.json, reddit_submissions.json
```

---

### Task 1: Core pipeline state module

**Files:**
- Create: `app/core/__init__.py`
- Create: `app/core/pipeline.py`
- Create: `app/tests/test_pipeline.py`
- Create: `app/tests/__init__.py`

**Interfaces:**
- Consumes: none
- Produces:
  - `def make_pipeline_state(step_defs: list[dict]) -> dict`
  - `def reset_pipeline(state: dict, step_defs: list[dict], profile_url: str = '', depth: str = '') -> None`
  - `def set_step(state: dict, step_id: str, status: str) -> None`
  - `def finish_pipeline(state: dict, error: str | None = None) -> None`
  - State keys: `running`, `profile_url`, `depth`, `steps`, `error`, `profile_id`, `started_at`, `finished_at`

- [ ] **Step 1: Write the failing test**

```python
# app/tests/test_pipeline.py
from core.pipeline import make_pipeline_state, reset_pipeline, set_step, finish_pipeline

STEPS = [
    {'id': 'about', 'label': 'About'},
    {'id': 'db', 'label': 'DB'},
]

def test_reset_sets_pending_steps():
    state = make_pipeline_state(STEPS)
    reset_pipeline(state, STEPS, profile_url='https://x', depth='light')
    assert state['profile_url'] == 'https://x'
    assert state['depth'] == 'light'
    assert state['running'] is False
    assert [s['status'] for s in state['steps']] == ['pending', 'pending']

def test_set_step_and_finish():
    state = make_pipeline_state(STEPS)
    reset_pipeline(state, STEPS)
    set_step(state, 'about', 'active')
    set_step(state, 'about', 'done')
    finish_pipeline(state, error=None)
    assert state['steps'][0]['status'] == 'done'
    assert state['error'] is None
    assert state['running'] is False
    assert state['finished_at'] is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/user/tool/birdy-edwards-lite && ./venv/bin/pip install pytest -q && cd app && ../venv/bin/pytest tests/test_pipeline.py -v`

Expected: FAIL (import error / module not found)

- [ ] **Step 3: Write minimal implementation**

```python
# app/core/__init__.py  (empty)

# app/core/pipeline.py
from datetime import datetime

def make_pipeline_state(step_defs):
    return {
        'running': False,
        'profile_url': '',
        'depth': '',
        'steps': [],
        'error': None,
        'profile_id': None,
        'started_at': None,
        'finished_at': None,
    }

def reset_pipeline(state, step_defs, profile_url='', depth=''):
    state.update({
        'running': False,
        'profile_url': profile_url,
        'depth': depth,
        'error': None,
        'profile_id': None,
        'started_at': None,
        'finished_at': None,
        'steps': [
            {'id': s['id'], 'label': s['label'], 'status': 'pending'}
            for s in step_defs
        ],
    })

def set_step(state, step_id, status):
    for s in state['steps']:
        if s['id'] == step_id:
            s['status'] = status
            break

def finish_pipeline(state, error=None):
    state['running'] = False
    state['error'] = error
    state['finished_at'] = datetime.utcnow().isoformat() + 'Z'
```

- [ ] **Step 4: Run tests and make sure they pass**

Run: `cd /home/user/tool/birdy-edwards-lite/app && ../venv/bin/pytest tests/test_pipeline.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /home/user/tool/birdy-edwards-lite
git add app/core/__init__.py app/core/pipeline.py app/tests/__init__.py app/tests/test_pipeline.py
git commit -m "feat(core): add shared pipeline step state helper"
```

---

### Task 2: URL normalizers (Instagram + Reddit)

**Files:**
- Create: `app/core/urls.py`
- Create: `app/tests/test_urls.py`

**Interfaces:**
- Consumes: none
- Produces:
  - `def normalize_instagram_target(raw: str) -> str`  # raises `ValueError`
  - `def normalize_reddit_target(raw: str) -> str`     # raises `ValueError`
  - Canonical forms: `https://www.instagram.com/<user>/` and `https://www.reddit.com/user/<name>/`

- [ ] **Step 1: Write the failing test**

```python
# app/tests/test_urls.py
import pytest
from core.urls import normalize_instagram_target, normalize_reddit_target

@pytest.mark.parametrize('raw,expected', [
    ('natgeo', 'https://www.instagram.com/natgeo/'),
    ('@natgeo', 'https://www.instagram.com/natgeo/'),
    ('https://www.instagram.com/natgeo', 'https://www.instagram.com/natgeo/'),
    ('https://instagram.com/natgeo/', 'https://www.instagram.com/natgeo/'),
])
def test_ig_ok(raw, expected):
    assert normalize_instagram_target(raw) == expected

@pytest.mark.parametrize('raw', [
    'https://www.instagram.com/p/ABC/',
    'https://www.instagram.com/explore/tags/x/',
    '',
])
def test_ig_reject(raw):
    with pytest.raises(ValueError):
        normalize_instagram_target(raw)

@pytest.mark.parametrize('raw,expected', [
    ('spez', 'https://www.reddit.com/user/spez/'),
    ('u/spez', 'https://www.reddit.com/user/spez/'),
    ('https://www.reddit.com/user/spez', 'https://www.reddit.com/user/spez/'),
    ('https://old.reddit.com/user/spez/', 'https://www.reddit.com/user/spez/'),
])
def test_reddit_ok(raw, expected):
    assert normalize_reddit_target(raw) == expected

@pytest.mark.parametrize('raw', [
    'https://www.reddit.com/r/python/',
    'https://www.reddit.com/search/?q=x',
    '',
])
def test_reddit_reject(raw):
    with pytest.raises(ValueError):
        normalize_reddit_target(raw)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/user/tool/birdy-edwards-lite/app && ../venv/bin/pytest tests/test_urls.py -v`  
Expected: FAIL (module not found)

- [ ] **Step 3: Write minimal implementation**

```python
# app/core/urls.py
import re
from urllib.parse import urlparse

_IG_USER = re.compile(r'^[A-Za-z0-9._]{1,30}$')
_RD_USER = re.compile(r'^[A-Za-z0-9_-]{3,20}$')

def normalize_instagram_target(raw: str) -> str:
    s = (raw or '').strip()
    if not s:
        raise ValueError('empty Instagram target')
    if s.startswith('@'):
        s = s[1:]
    if '://' not in s and '/' not in s:
        if not _IG_USER.match(s):
            raise ValueError(f'invalid Instagram username: {s}')
        return f'https://www.instagram.com/{s}/'
    u = urlparse(s if '://' in s else 'https://' + s)
    host = (u.hostname or '').lower().replace('www.', '')
    if host not in ('instagram.com',):
        raise ValueError('not an Instagram URL')
    parts = [p for p in u.path.split('/') if p]
    reserved = {'p', 'reel', 'reels', 'stories', 'explore', 'accounts', 'direct'}
    if not parts or parts[0].lower() in reserved:
        raise ValueError('Instagram target must be a profile URL or username')
    user = parts[0]
    if not _IG_USER.match(user):
        raise ValueError(f'invalid Instagram username: {user}')
    return f'https://www.instagram.com/{user}/'

def normalize_reddit_target(raw: str) -> str:
    s = (raw or '').strip()
    if not s:
        raise ValueError('empty Reddit target')
    if s.lower().startswith('u/'):
        s = s[2:]
    if '://' not in s and '/' not in s:
        if not _RD_USER.match(s):
            raise ValueError(f'invalid Reddit username: {s}')
        return f'https://www.reddit.com/user/{s}/'
    u = urlparse(s if '://' in s else 'https://' + s)
    host = (u.hostname or '').lower()
    if host not in ('reddit.com', 'www.reddit.com', 'old.reddit.com', 'www.old.reddit.com'):
        raise ValueError('not a Reddit URL')
    parts = [p for p in u.path.split('/') if p]
    if len(parts) >= 2 and parts[0].lower() in ('user', 'u'):
        name = parts[1]
        if not _RD_USER.match(name):
            raise ValueError(f'invalid Reddit username: {name}')
        return f'https://www.reddit.com/user/{name}/'
    raise ValueError('Reddit target must be a user profile')
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `cd /home/user/tool/birdy-edwards-lite/app && ../venv/bin/pytest tests/test_urls.py -v`

- [ ] **Step 5: Commit**

```bash
git add app/core/urls.py app/tests/test_urls.py
git commit -m "feat(core): add Instagram and Reddit target URL normalizers"
```

---

### Task 3: Legacy FB DB rename helper

**Files:**
- Create: `app/core/db_base.py`
- Create: `app/tests/test_db_migrate.py`

**Interfaces:**
- Consumes: stdlib `os`
- Produces:
  - `def migrate_legacy_fb_db(app_dir: str, legacy_name: str = 'socmint_lite.db', new_name: str = 'socmint_fb.db') -> str`
  - Returns absolute path to the FB DB to use. If `legacy` exists and `new` does not → rename. If both exist → prefer `new`. If neither → return path to `new`.

- [ ] **Step 1: Write the failing test**

```python
# app/tests/test_db_migrate.py
import os
from core.db_base import migrate_legacy_fb_db

def test_renames_legacy(tmp_path):
    legacy = tmp_path / 'socmint_lite.db'
    legacy.write_bytes(b'sqlite')
    path = migrate_legacy_fb_db(str(tmp_path))
    assert path.endswith('socmint_fb.db')
    assert os.path.exists(path)
    assert not os.path.exists(legacy)

def test_prefers_new_when_both(tmp_path):
    (tmp_path / 'socmint_lite.db').write_bytes(b'old')
    new = tmp_path / 'socmint_fb.db'
    new.write_bytes(b'new')
    path = migrate_legacy_fb_db(str(tmp_path))
    assert path == str(new)
    assert (tmp_path / 'socmint_lite.db').exists()

def test_returns_new_path_when_missing(tmp_path):
    path = migrate_legacy_fb_db(str(tmp_path))
    assert path.endswith('socmint_fb.db')
    assert not os.path.exists(path)
```

- [ ] **Step 2: Run — expect FAIL**

Run: `cd /home/user/tool/birdy-edwards-lite/app && ../venv/bin/pytest tests/test_db_migrate.py -v`

- [ ] **Step 3: Implement**

```python
# app/core/db_base.py
import os
import sqlite3

def migrate_legacy_fb_db(app_dir, legacy_name='socmint_lite.db', new_name='socmint_fb.db'):
    legacy = os.path.join(app_dir, legacy_name)
    new = os.path.join(app_dir, new_name)
    if os.path.exists(new):
        return new
    if os.path.exists(legacy):
        os.rename(legacy, new)
        return new
    return new

def connect(db_file):
    con = sqlite3.connect(db_file)
    con.row_factory = sqlite3.Row
    return con
```

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add app/core/db_base.py app/tests/test_db_migrate.py
git commit -m "feat(core): migrate socmint_lite.db to socmint_fb.db"
```

---

### Task 4: Move scoring + face into `core/`

**Files:**
- Create: `app/core/scoring.py` (copy from `commentor_scoring_lite.py`)
- Create: `app/core/face.py` (copy from `face_intelligence_lite.py`)
- Modify: thin shims `app/commentor_scoring_lite.py` and `app/face_intelligence_lite.py` re-export from `core` (removed after Task 5)
- Test: `app/tests/test_scoring_smoke.py`

**Interfaces:**
- Consumes: SQLite schema with `commentor_frequency`, `commentors`, `top7_profiles`, `photo_posts`, etc.
- Produces:
  - `get_profile_id(db_file)`, `get_all_interactors(db_file, profile_id=None)`, `get_top7(...)`, `get_graph_data(...)`, `get_cocomment_graph(...)`, `get_interaction_timeline(...)`, `get_post_type_counts(...)`, `get_profile_summary(...)`
  - `run_face_clustering(db_file: str, profile_id: int) -> None`

- [ ] **Step 1: Write failing smoke test**

```python
# app/tests/test_scoring_smoke.py
import sqlite3
from core.scoring import get_all_interactors

SCHEMA_MIN = """
CREATE TABLE profiles (id INTEGER PRIMARY KEY, profile_url TEXT, owner_name TEXT);
CREATE TABLE commentors (id INTEGER PRIMARY KEY, profile_url TEXT UNIQUE, name TEXT);
CREATE TABLE commentor_frequency (
  id INTEGER PRIMARY KEY, profile_id INT, commentor_id INT,
  photo_count INT, reel_count INT, text_count INT, total_count INT
);
"""

def test_get_all_interactors(tmp_path):
    db = str(tmp_path / 't.db')
    con = sqlite3.connect(db)
    con.executescript(SCHEMA_MIN)
    con.execute("INSERT INTO profiles VALUES (1,'https://x','X')")
    con.execute("INSERT INTO commentors VALUES (1,'https://y','Y')")
    con.execute("INSERT INTO commentor_frequency VALUES (1,1,1,2,0,1,3)")
    con.commit(); con.close()
    rows = get_all_interactors(db, 1)
    assert rows[0]['name'] == 'Y'
    assert rows[0]['total_count'] == 3
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Move code** — copy `commentor_scoring_lite.py` → `core/scoring.py`; copy `face_intelligence_lite.py` → `core/face.py`. Add shims:

```python
# app/commentor_scoring_lite.py
from core.scoring import *  # noqa
DB_FILE = 'socmint_fb.db'

# app/face_intelligence_lite.py
from core.face import *  # noqa
```

- [ ] **Step 4: Run — expect PASS** (`pytest tests/test_scoring_smoke.py -v`)

- [ ] **Step 5: Commit**

```bash
git add app/core/scoring.py app/core/face.py app/commentor_scoring_lite.py app/face_intelligence_lite.py app/tests/test_scoring_smoke.py
git commit -m "refactor(core): move scoring and face clustering into shared core"
```

---

### Task 5: Facebook platform package + blueprint (behavior-preserving)

**Files:**
- Create: `app/platforms/__init__.py`, `app/platforms/facebook/__init__.py`
- Create: `app/platforms/facebook/constants.py`
- Create: `app/platforms/facebook/db.py` (from `socmint_lite_db.py`; default `socmint_fb.db`)
- Move scrapers under `platforms/facebook/` (`about_sb.py`, `photos_sb.py`, `reels_sb.py`, `posts_sb.py`)
- Create: `app/platforms/facebook/blueprint.py` (routes from current `app.py`)
- Move templates to `app/templates/facebook/`
- Create: `app/templates/_shell.html` with platform tabs
- Rewrite: `app/app.py` thin shell
- Test: `app/tests/test_facebook_blueprint.py`

**Interfaces:**
- Consumes: `core.pipeline`, `core.scoring`, `core.face`, `core.db_base.migrate_legacy_fb_db`
- Produces: `facebook_bp` with `url_prefix='/facebook'` and routes mirroring current APIs under that prefix

- [ ] **Step 1: Write failing blueprint smoke test**

```python
# app/tests/test_facebook_blueprint.py
import importlib.util, os

def _load_app():
    path = os.path.join(os.path.dirname(__file__), '..', 'app.py')
    spec = importlib.util.spec_from_file_location('birdy_app', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.app

def test_root_redirects_to_facebook():
    client = _load_app().test_client()
    r = client.get('/', follow_redirects=False)
    assert r.status_code in (301, 302)
    assert '/facebook' in r.headers.get('Location', '')

def test_facebook_home_ok():
    client = _load_app().test_client()
    r = client.get('/facebook/')
    assert r.status_code == 200
```

- [ ] **Step 2: Run — expect FAIL** (no `/facebook` yet)

- [ ] **Step 3: Implement move**

`platforms/facebook/constants.py` — `BASE_DIR` = three `dirname`s up from this file (to `app/`), `COOKIE_FILE=fb_cookies.pkl`, `DB_FILE=socmint_fb.db`, same `DEPTH_LIMITS` / `PIPELINE_STEPS` as current `app.py`.

Move handlers into `blueprint.py`:
- templates → `facebook/index.html`, `facebook/analysis.html`
- pipeline state via `core.pipeline` owned by the blueprint module
- scrapers from `platforms.facebook.*_sb`
- on app create: `migrate_legacy_fb_db(BASE_DIR)` then `init_db(DB_FILE)`

Thin `app.py`:

```python
import os
from flask import Flask, redirect

from core.db_base import migrate_legacy_fb_db
from platforms.facebook.blueprint import facebook_bp
from platforms.facebook.db import init_db
from platforms.facebook.constants import BASE_DIR, DB_FILE

def create_app():
    migrate_legacy_fb_db(BASE_DIR)
    init_db(DB_FILE)
    application = Flask(
        __name__,
        template_folder=os.path.join(BASE_DIR, 'templates'),
        static_folder=os.path.join(BASE_DIR, 'static'),
    )
    application.secret_key = os.environ.get('SECRET_KEY') or os.urandom(32)
    application.register_blueprint(facebook_bp)

    @application.route('/')
    def root():
        return redirect('/facebook/')

    return application

app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
```

Update scrapers to import `COOKIE_FILE` from `platforms.facebook.constants`. Leave temporary shims for old module names if needed, then delete once imports are clean.

- [ ] **Step 4: Run tests + manual FB home/investigation open**

```bash
cd /home/user/tool/birdy-edwards-lite/app && ../venv/bin/pytest tests/ -v
```

- [ ] **Step 5: Commit**

```bash
git add -A app/core app/platforms/facebook app/templates app/app.py app/tests
git commit -m "refactor: extract Facebook into platform blueprint under shared core"
```

---

### Task 6: Core browser cookie helpers

**Files:**
- Create: `app/core/browser.py`
- Create: `app/tests/test_browser_cookies.py`

**Interfaces:**
- Produces:
  - `def cookies_have_domain(cookies: list[dict], domain_substr: str) -> bool`
  - `def save_cookies_pickle(path: str, cookies: list[dict]) -> None`
  - `def load_cookies_pickle(path: str) -> list[dict]`
  - `def filter_cookies_for_domain(cookies: list[dict], domain_substr: str) -> list[dict]`

- [ ] **Step 1: Failing tests**

```python
from core.browser import (
    cookies_have_domain, filter_cookies_for_domain,
    save_cookies_pickle, load_cookies_pickle,
)

def test_domain_helpers():
    cookies = [
        {'name': 'c_user', 'value': '1', 'domain': '.facebook.com'},
        {'name': 'sessionid', 'value': 'x', 'domain': '.instagram.com'},
    ]
    assert cookies_have_domain(cookies, 'instagram.com') is True
    assert cookies_have_domain(cookies, 'reddit.com') is False
    ig = filter_cookies_for_domain(cookies, 'instagram.com')
    assert len(ig) == 1 and ig[0]['name'] == 'sessionid'

def test_pickle_roundtrip(tmp_path):
    path = str(tmp_path / 'c.pkl')
    save_cookies_pickle(path, [{'name': 'a', 'value': 'b', 'domain': '.x.com'}])
    assert load_cookies_pickle(path)[0]['name'] == 'a'
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement `browser.py`** with pickle + domain substring checks (`domain_substr in cookie.get('domain','')`)

- [ ] **Step 4: PASS; optionally refactor FB cookie import to use helpers**

- [ ] **Step 5: Commit** `feat(core): shared cookie pickle helpers`

---

### Task 7: Instagram DB + fixture import

**Files:**
- Create: `app/platforms/instagram/__init__.py`, `constants.py`, `db.py`
- Create: `app/tests/fixtures/ig_about.json`, `ig_posts.json`, `ig_reels.json`
- Create: `app/tests/test_ig_db_import.py`

**Interfaces:**
- Produces: `init_db(db_file)`, `import_all(about_json, posts_json, reels_json, db_file)`, `compute_frequency(db_file, profile_id)`, `extract_top7(db_file, profile_id)`
- Schema table names match FB so `core.scoring` / `core.face` work (`photo_posts` for feed posts, `reel_posts`, comments, `commentor_frequency`, `top7_*`, `face_*`)

**Fixture shapes:**

```json
{
  "profile_url": "https://www.instagram.com/example/",
  "owner_name": "Example User",
  "username": "example",
  "is_locked": false,
  "bio": "hello",
  "website": "https://example.com",
  "followers": 10,
  "following": 5,
  "post_count": 3,
  "sections": {
    "profile": [
      {"field_type": "bio", "label": "Bio", "value": "hello"},
      {"field_type": "website", "label": "Website", "value": "https://example.com"}
    ]
  }
}
```

```json
[{
  "post_url": "https://www.instagram.com/p/AAA/",
  "date": "2026-01-01",
  "caption": "hi",
  "image_src": "https://example.com/a.jpg",
  "media_type": "image",
  "comments": [
    {"name": "bob", "profile_url": "https://www.instagram.com/bob/", "comment_text": "nice"}
  ]
}]
```

```json
[{
  "reel_url": "https://www.instagram.com/reel/BBB/",
  "date": "2026-01-02",
  "caption": "reel",
  "comments": [
    {"name": "bob", "profile_url": "https://www.instagram.com/bob/", "comment_text": "fire"}
  ]
}]
```

- [ ] **Step 1: Write `test_ig_db_import.py`** — after import + frequency, bob `total_count == 2`

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement `db.py` + `constants.py`**

```python
# constants highlights
COOKIE_FILE = ... 'ig_cookies.pkl'
DB_FILE = ... 'socmint_ig.db'
DEPTH_LIMITS = {
    'light':  {'posts': 5,  'reels': 5},
    'medium': {'posts': 10, 'reels': 10},
    'deep':   {'posts': 20, 'reels': 20},
}
PIPELINE_STEPS = [
    {'id': 'about', 'label': 'Scraping — Profile'},
    {'id': 'posts', 'label': 'Scraping — Posts + Comments'},
    {'id': 'reels', 'label': 'Scraping — Reels + Comments'},
    {'id': 'db', 'label': 'Database Import'},
    {'id': 'frequency', 'label': 'Frequency Scoring'},
    {'id': 'top7', 'label': 'Top 7 Metadata Gather'},
    {'id': 'face', 'label': 'Face Clustering'},
]
```

- [ ] **Step 4: PASS**

- [ ] **Step 5: Commit** `feat(instagram): add SQLite schema and fixture import`

---

### Task 8: Instagram scrapers (SeleniumBase)

**Files:**
- Create: `app/platforms/instagram/about_sb.py`, `posts_sb.py`, `reels_sb.py`
- Create: `app/tests/fixtures/ig_profile_snippet.html`
- Create: `app/tests/test_ig_about_parse.py`

**Interfaces:**
- `about_sb.main(PROFILE_URL: str) -> None` → `ig_about.json`
- `posts_sb.main(PROFILE_URL: str, MAX_POSTS: int = 10) -> None` → `ig_posts.json`
- `reels_sb.main(PROFILE_URL: str, MAX_REELS: int = 10) -> None` → `ig_reels.json`
- `parse_profile_from_html(html: str, profile_url: str) -> dict` for unit testing
- JSON contracts = Task 7 fixtures; raise if cookies missing / not logged in

- [ ] **Step 1: Failing parse test** with synthetic HTML fixture containing username + bio

- [ ] **Step 2: FAIL**

- [ ] **Step 3: Implement scrapers** (Xvfb + cookie login like FB; extract profile/posts/reels; verify selectors against authorized live session; keep JSON contract stable)

- [ ] **Step 4: Unit PASS + manual shallow smoke**

- [ ] **Step 5: Commit** `feat(instagram): add about/posts/reels SeleniumBase scrapers`

---

### Task 9: Instagram blueprint + UI

**Files:**
- Create: `app/platforms/instagram/blueprint.py`
- Create: `app/templates/instagram/index.html`, `analysis.html`
- Modify: `app/app.py` register `instagram_bp`
- Enable Instagram tab in `_shell.html`
- Test: `app/tests/test_instagram_blueprint.py`

**Interfaces:**
- `instagram_bp` at `/instagram` with cookie import/verify, start-pipeline (uses `normalize_instagram_target`), pipeline-status, investigations CRUD, analysis APIs mirroring Facebook (including face)

- [ ] **Step 1: Failing test** — `GET /instagram/` → 200; invalid post URL start-pipeline → 400

- [ ] **Step 2: FAIL**

- [ ] **Step 3: Clone Facebook blueprint**, swap IG constants/scrapers/db, register in `create_app()`

- [ ] **Step 4: pytest PASS**

- [ ] **Step 5: Commit** `feat(instagram): add mini-app blueprint and templates`

---

### Task 10: Reddit DB + fixture import

**Files:**
- Create: `app/platforms/reddit/__init__.py`, `constants.py`, `db.py`
- Create: fixtures `reddit_about.json`, `reddit_submissions.json`
- Create: `app/tests/test_reddit_db_import.py`

**Interfaces:**
- `init_db`, `import_all(about_json, submissions_json, db_file)`, `compute_frequency`, `extract_top7`
- Submissions map to `text_posts` with extra `title`, `subreddit`, `body` columns; comments → `text_comments`; frequency increments `text_count` only; no face tables required for pipeline (may create stubs)

**Fixtures:**

```json
{
  "profile_url": "https://www.reddit.com/user/example/",
  "owner_name": "example",
  "is_locked": false,
  "sections": {
    "profile": [
      {"field_type": "karma", "label": "Post Karma", "value": "123"},
      {"field_type": "cake_day", "label": "Cake Day", "value": "2020-01-01"}
    ]
  }
}
```

```json
[{
  "post_url": "https://www.reddit.com/r/test/comments/abc/title/",
  "title": "Hello",
  "subreddit": "test",
  "date": "2026-01-01",
  "body": "world",
  "score": 10,
  "comments": [
    {"name": "alice", "profile_url": "https://www.reddit.com/user/alice/", "comment_text": "hi"}
  ]
}]
```

- [ ] **Step 1: Test import → frequency → alice `total_count == 1`**

- [ ] **Step 2: FAIL**

- [ ] **Step 3: Implement** — `PIPELINE_STEPS` without face; `COOKIE_FILE=reddit_cookies.pkl`; `DB_FILE=socmint_reddit.db`; depth caps on `posts` only

- [ ] **Step 4: PASS**

- [ ] **Step 5: Commit** `feat(reddit): add SQLite schema and fixture import`

---

### Task 11: Reddit scrapers

**Files:**
- Create: `app/platforms/reddit/about_sb.py`, `submissions_sb.py`
- Create: HTML fixtures + `app/tests/test_reddit_about_parse.py`

**Interfaces:**
- `about_sb.main(PROFILE_URL: str) -> None` → `reddit_about.json`
- `submissions_sb.main(PROFILE_URL: str, MAX_POSTS: int = 10) -> None` → `reddit_submissions.json`
- Prefer `old.reddit.com` HTML when session allows

- [ ] **Step 1: Failing parse tests** for profile + submission list snippets

- [ ] **Step 2: FAIL**

- [ ] **Step 3: Implement scrapers** (cookie login; `/user/<name>/submitted/`; harvest comment authors; keep Task 10 JSON contract)

- [ ] **Step 4: Unit PASS + manual smoke**

- [ ] **Step 5: Commit** `feat(reddit): add about and submissions SeleniumBase scrapers`

---

### Task 12: Reddit blueprint + UI

**Files:**
- Create: `app/platforms/reddit/blueprint.py`
- Create: `app/templates/reddit/index.html`, `analysis.html` (no face section)
- Modify: `app/app.py` register `reddit_bp`
- Enable Reddit tab
- Test: `app/tests/test_reddit_blueprint.py`

**Interfaces:**
- Same route pattern under `/reddit`; `normalize_reddit_target`; pipeline **without** face; analysis APIs return empty face payloads

- [ ] **Step 1: Failing tests** — home 200; reject `/r/python/` with 400

- [ ] **Step 2: FAIL**

- [ ] **Step 3: Implement blueprint**

- [ ] **Step 4: PASS**

- [ ] **Step 5: Commit** `feat(reddit): add mini-app blueprint and templates`

---

### Task 13: Analysis parity polish + readme

**Files:**
- Modify: IG/Reddit analysis templates — all API paths platform-prefixed
- Modify: `readme.md` — three tabs, cookie/DB names, targets
- Test: `app/tests/test_api_prefixes.py`

- [ ] **Step 1: Write test** asserting ig/reddit template sources contain `/instagram/api/` or `/reddit/api/` and not bare `fetch('/api/`

- [ ] **Step 2: FAIL if bare paths remain**

- [ ] **Step 3: Fix templates + update readme**

- [ ] **Step 4: Full `pytest` + manual click-through all three homes**

- [ ] **Step 5: Commit** `docs: document Instagram and Reddit mini-apps; fix API path prefixes`

---

## Spec coverage checklist (self-review)

| Spec requirement | Task |
|---|---|
| Platform packages + shared core | 1–6, 5 |
| Separate mini-apps / tabs | 5, 9, 12 |
| Cookie + SeleniumBase auth | 6, 8, 11 |
| FB DB rename migration | 3, 5 |
| `/` → `/facebook` | 5 |
| IG about/posts/reels + comments + faces | 7–9 |
| Reddit about/submissions + comments, no face | 10–12 |
| URL normalizers | 2, 9, 12 |
| Frequency + top7 + graphs | 4, 7, 9, 10, 12 |
| Readme | 13 |
| No Stories / no subreddit targets / no official APIs | 2, 8, 11 |

**Placeholder scan:** none — live DOM selectors explicitly verified at implementation time while JSON contracts stay fixed.

**Type consistency:** `normalize_*_target(raw: str) -> str`; scraper `main(...)` naming; DB/cookie filenames match spec.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-23-instagram-reddit-modules.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks  
2. **Inline Execution** — run tasks in this session with executing-plans and checkpoints  

Which approach?
