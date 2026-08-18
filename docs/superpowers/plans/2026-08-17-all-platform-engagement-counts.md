# All-Platform Engagement Counts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every mini-app (Facebook, Instagram, Reddit, Threads, Telegram, X) scrapes Like / Comment / Repost **counts** the X.com way (HTML parse, post-row columns, no liker lists), shows them on home + analysis (X metrics row + Telegram stacked Activity Timeline), and includes them in PDF/JSON.

**Architecture:** Shared `core/counts.py` (compact ints + column migrate) and `core/engagement_metrics.py` (activity-metrics API payload). Each platform parser writes `like_count`, `reply_count` (UI: Comment), `repost_count` onto `photo_posts` / `reel_posts` / `text_posts`. X already has counts; other platforms add migrate + parse. Do not add reaction/share people tables. Spec: `docs/superpowers/specs/2026-08-17-facebook-engagement-design.md`.

**Tech Stack:** Python 3.12, Flask blueprints, SeleniumBase, SQLite, pytest, Chart.js (already in analysis templates), reportlab.

## Global Constraints

- Dashboard labels: **Like / Comment / Repost** (X Reply → Comment; FB Share → Repost; TG Forward → Repost; Reddit score → Like)
- API JSON keys: `like`, `comment`, `repost` (X also `view`)
- DB columns: `like_count`, `reply_count`, `repost_count` INTEGER DEFAULT 0 (X keeps `view_count`)
- Scrape: compact-int parse from visible labels / JSON; **no actor lists** for likes or reposts
- Existing comment-people harvest stays
- Do not open Facebook reaction/share dialogs or Instagram like-lists
- Instagram/Reddit with no public repost number: `repost_count = 0`
- Missing parse → store 0; do not fill from `COUNT(*)` of commenter rows
- Old JSON without count keys still imports (zeros)
- Frequency / Top 7 / graphs stay commenter-based; do not add likers
- Tests: `cd /home/user/tool/birdy-edwards-lite-v2/app && python -m pytest …`
- Authorized-use / cookies-only scrape unchanged
- Do not change Telegram word-analysis or add Views on non-X platforms

---

## File Structure

```
app/core/counts.py
app/core/engagement_metrics.py
app/platforms/facebook/counts_parse.py
app/platforms/*/db.py, *sb.py, blueprint.py
app/templates/*/index.html, analysis.html
app/core/report.py
app/tests/test_counts.py
app/tests/test_engagement_metrics.py
app/tests/test_facebook_counts_parse.py
app/tests/fixtures/fb_engagement_snippet.html
```

---

### Task 1: Shared compact-int + column migrate

**Files:**
- Create: `app/core/counts.py`
- Test: `app/tests/test_counts.py`

**Interfaces:**
- Consumes: none
- Produces:
  - `def parse_compact_int(num: str | None, suffix: str | None = None) -> int | None`
  - `def as_int(value, default: int = 0) -> int`
  - `ENGAGEMENT_COLS = ('like_count', 'reply_count', 'repost_count')`
  - `def ensure_engagement_columns(con, tables: tuple[str, ...] = ('photo_posts', 'reel_posts', 'text_posts')) -> None`

- [ ] **Step 1: Write the failing test**

```python
# app/tests/test_counts.py
import sqlite3
from core.counts import parse_compact_int, as_int, ensure_engagement_columns


def test_parse_compact_int():
    assert parse_compact_int('12') == 12
    assert parse_compact_int('1.2', 'K') == 1200
    assert parse_compact_int('.') is None
    assert as_int(None) == 0
    assert as_int('3') == 3


def test_ensure_engagement_columns(tmp_path):
    con = sqlite3.connect(str(tmp_path / 't.db'))
    con.execute('CREATE TABLE text_posts (id INTEGER PRIMARY KEY, post_url TEXT)')
    con.execute('CREATE TABLE photo_posts (id INTEGER PRIMARY KEY)')
    ensure_engagement_columns(con)
    for table in ('text_posts', 'photo_posts'):
        cols = {r[1] for r in con.execute(f'PRAGMA table_info({table})')}
        assert {'like_count', 'reply_count', 'repost_count'} <= cols
    ensure_engagement_columns(con, tables=('no_such_table',))
    con.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/user/tool/birdy-edwards-lite-v2/app && python -m pytest tests/test_counts.py -v`

Expected: FAIL with `ModuleNotFoundError` for `core.counts`

- [ ] **Step 3: Write minimal implementation**

```python
# app/core/counts.py
import re

ENGAGEMENT_COLS = ('like_count', 'reply_count', 'repost_count')


def parse_compact_int(num, suffix=None):
    if num is None:
        return None
    s = str(num).strip().replace(',', '').replace('\u00a0', '').replace(' ', '')
    if not s or s in {'.', ','}:
        return None
    match = re.match(r'^(\d*\.?\d+)\s*([kmb])?$', s, re.I)
    if match:
        try:
            value = float(match.group(1))
        except ValueError:
            return None
        suf = (match.group(2) or suffix or '').lower()
        return int(value * {'k': 1_000, 'm': 1_000_000, 'b': 1_000_000_000}.get(suf, 1))
    digits = re.sub(r'[^\d]', '', s)
    return int(digits) if digits else None


def as_int(value, default=0):
    if value is None or value == '':
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    parsed = parse_compact_int(str(value))
    return default if parsed is None else parsed


def ensure_engagement_columns(con, tables=('photo_posts', 'reel_posts', 'text_posts')):
    cur = con.cursor()
    for table in tables:
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        )
        if not cur.fetchone():
            continue
        cur.execute(f'PRAGMA table_info({table})')
        cols = {row[1] for row in cur.fetchall()}
        for col in ENGAGEMENT_COLS:
            if col not in cols:
                cur.execute(f'ALTER TABLE {table} ADD COLUMN {col} INTEGER DEFAULT 0')
    con.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/user/tool/birdy-edwards-lite-v2/app && python -m pytest tests/test_counts.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/core/counts.py app/tests/test_counts.py
git commit -m "feat: shared compact-int and engagement column migrate"
```

---

### Task 2: Shared activity-metrics aggregator

**Files:**
- Create: `app/core/engagement_metrics.py`
- Test: `app/tests/test_engagement_metrics.py`

**Interfaces:**
- Consumes: `ensure_engagement_columns`
- Produces: `def get_activity_metrics(db_file: str, profile_id: int) -> dict` with `total_like`, `total_comment`, `total_repost`, `by_date`, `by_weekday` (Monday–Sunday), `by_hour` (0–23), `has_hour_data`
- UNION photo/reel/text for `profile_id`; skip missing tables; weekday only when `date_text` starts with `YYYY-MM-DD`

- [ ] **Step 1: Write the failing test**

```python
# app/tests/test_engagement_metrics.py
import sqlite3
from core.counts import ensure_engagement_columns
from core.engagement_metrics import get_activity_metrics


def _seed(path):
    con = sqlite3.connect(path)
    con.executescript(
        '''
        CREATE TABLE profiles (id INTEGER PRIMARY KEY);
        CREATE TABLE text_posts (
            id INTEGER PRIMARY KEY, profile_id INTEGER, post_url TEXT UNIQUE,
            date_text TEXT
        );
        INSERT INTO profiles (id) VALUES (1);
        '''
    )
    ensure_engagement_columns(con, tables=('text_posts',))
    con.execute(
        '''INSERT INTO text_posts
           (profile_id, post_url, date_text, like_count, reply_count, repost_count)
           VALUES (1, 'u1', '2026-08-03', 10, 2, 1)'''
    )
    con.execute(
        '''INSERT INTO text_posts
           (profile_id, post_url, date_text, like_count, reply_count, repost_count)
           VALUES (1, 'u2', 'not-a-date', 5, 0, 0)'''
    )
    con.commit()
    con.close()


def test_activity_metrics_stacks_like_comment_repost(tmp_path):
    db = str(tmp_path / 'm.db')
    _seed(db)
    data = get_activity_metrics(db, 1)
    assert data['total_like'] == 15
    assert data['total_comment'] == 2
    assert data['total_repost'] == 1
    by_date = {r['date']: r for r in data['by_date']}
    assert by_date['2026-08-03']['like'] == 10
    assert by_date['not-a-date']['like'] == 5
    monday = next(r for r in data['by_weekday'] if r['day'] == 'Monday')
    assert monday['like'] == 10
    assert data['has_hour_data'] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/user/tool/birdy-edwards-lite-v2/app && python -m pytest tests/test_engagement_metrics.py -v`

Expected: FAIL importing `core.engagement_metrics`

- [ ] **Step 3: Write minimal implementation**

```python
# app/core/engagement_metrics.py
import sqlite3
from collections import defaultdict
from datetime import datetime

from core.counts import ensure_engagement_columns

_DAY_NAMES = (
    'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday',
)


def _table_names(cur):
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    return {r[0] for r in cur.fetchall()}


def _fetch_rows(cur, tables, profile_id):
    rows = []
    for table in tables:
        cur.execute(
            f'''
            SELECT date_text,
                   COALESCE(like_count, 0),
                   COALESCE(reply_count, 0),
                   COALESCE(repost_count, 0)
            FROM {table}
            WHERE profile_id = ?
            ''',
            (profile_id,),
        )
        for date_text, like, comment, repost in cur.fetchall():
            rows.append((date_text or '', int(like), int(comment), int(repost)))
    return rows


def get_activity_metrics(db_file: str, profile_id: int) -> dict:
    empty = {
        'total_like': 0,
        'total_comment': 0,
        'total_repost': 0,
        'by_date': [],
        'by_weekday': [{'day': d, 'like': 0, 'comment': 0, 'repost': 0} for d in _DAY_NAMES],
        'by_hour': [{'hour': h, 'like': 0, 'comment': 0, 'repost': 0} for h in range(24)],
        'has_hour_data': False,
    }
    if not profile_id:
        return empty
    con = sqlite3.connect(db_file)
    present = _table_names(con.cursor())
    tables = tuple(t for t in ('photo_posts', 'reel_posts', 'text_posts') if t in present)
    if tables:
        ensure_engagement_columns(con, tables=tables)
    cur = con.cursor()
    rows = _fetch_rows(cur, tables, profile_id)
    con.close()

    total_like = total_comment = total_repost = 0
    by_date = defaultdict(lambda: {'like': 0, 'comment': 0, 'repost': 0})
    by_wd = {d: {'like': 0, 'comment': 0, 'repost': 0} for d in _DAY_NAMES}
    by_hour = {h: {'like': 0, 'comment': 0, 'repost': 0} for h in range(24)}
    has_hour = False

    for date_text, like, comment, repost in rows:
        total_like += like
        total_comment += comment
        total_repost += repost
        key = date_text or '—'
        by_date[key]['like'] += like
        by_date[key]['comment'] += comment
        by_date[key]['repost'] += repost
        iso = None
        hour = None
        if date_text and len(date_text) >= 10 and date_text[4] == '-' and date_text[7] == '-':
            try:
                iso = datetime.strptime(date_text[:10], '%Y-%m-%d')
            except ValueError:
                iso = None
        if date_text and ('T' in date_text or (len(date_text) >= 13 and date_text[10] == ' ')):
            chunk = date_text.replace('T', ' ')
            try:
                hour = int(chunk[11:13])
                if 0 <= hour <= 23:
                    has_hour = True
                else:
                    hour = None
            except ValueError:
                hour = None
        if iso is not None:
            dname = _DAY_NAMES[iso.weekday()]
            by_wd[dname]['like'] += like
            by_wd[dname]['comment'] += comment
            by_wd[dname]['repost'] += repost
        if hour is not None:
            by_hour[hour]['like'] += like
            by_hour[hour]['comment'] += comment
            by_hour[hour]['repost'] += repost

    return {
        'total_like': total_like,
        'total_comment': total_comment,
        'total_repost': total_repost,
        'by_date': [
            {'date': d, **v} for d, v in sorted(by_date.items(), key=lambda x: x[0])
        ],
        'by_weekday': [{'day': d, **by_wd[d]} for d in _DAY_NAMES],
        'by_hour': [{'hour': h, **by_hour[h]} for h in range(24)],
        'has_hour_data': has_hour,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/user/tool/birdy-edwards-lite-v2/app && python -m pytest tests/test_engagement_metrics.py tests/test_counts.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/core/engagement_metrics.py app/tests/test_engagement_metrics.py
git commit -m "feat: shared like/comment/repost activity metrics"
```

---

### Task 3: Facebook HTML count parser

**Files:**
- Create: `app/platforms/facebook/counts_parse.py`
- Create: `app/tests/fixtures/fb_engagement_snippet.html`
- Test: `app/tests/test_facebook_counts_parse.py`

**Interfaces:**
- Consumes: `parse_compact_int`
- Produces: `def parse_facebook_engagement(html: str) -> dict` with `like_count`, `reply_count`, `repost_count` (default 0)
  - Like ← All reactions / reactions; Comment ← comments; Repost ← shares / reposts

- [ ] **Step 1: Write fixture + failing test**

`app/tests/fixtures/fb_engagement_snippet.html`:

```html
<div aria-label="All reactions: 1.2K">1.2K</div>
<span>45 comments</span>
<span>12 shares</span>
```

```python
# app/tests/test_facebook_counts_parse.py
import os
from platforms.facebook.counts_parse import parse_facebook_engagement

FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')


def test_parse_facebook_engagement_footer():
    html = open(os.path.join(FIXTURES, 'fb_engagement_snippet.html'), encoding='utf-8').read()
    got = parse_facebook_engagement(html)
    assert got == {'like_count': 1200, 'reply_count': 45, 'repost_count': 12}


def test_parse_facebook_engagement_missing():
    assert parse_facebook_engagement('hello') == {
        'like_count': 0, 'reply_count': 0, 'repost_count': 0,
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/user/tool/birdy-edwards-lite-v2/app && python -m pytest tests/test_facebook_counts_parse.py -v`

Expected: FAIL importing `counts_parse`

- [ ] **Step 3: Write parser**

```python
# app/platforms/facebook/counts_parse.py
import re
from core.counts import parse_compact_int

_COUNT = re.compile(
    r'(\d[\d,]*(?:\.\d+)?)\s*([KMB])?\s*'
    r'(All reactions|reactions?|comments?|shares?|reposts?)',
    re.I,
)


def parse_facebook_engagement(html: str) -> dict:
    out = {'like_count': 0, 'reply_count': 0, 'repost_count': 0}
    for match in _COUNT.finditer(html or ''):
        n = parse_compact_int(match.group(1), match.group(2))
        if n is None:
            continue
        kind = match.group(3).lower()
        if 'reaction' in kind:
            out['like_count'] = n
        elif 'comment' in kind:
            out['reply_count'] = n
        elif 'share' in kind or 'repost' in kind:
            out['repost_count'] = n
    return out
```

- [ ] **Step 4: Run tests**

Run: `cd /home/user/tool/birdy-edwards-lite-v2/app && python -m pytest tests/test_facebook_counts_parse.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/platforms/facebook/counts_parse.py app/tests/test_facebook_counts_parse.py app/tests/fixtures/fb_engagement_snippet.html
git commit -m "feat: parse Facebook post footer like/comment/share counts"
```

---

### Task 4: Facebook DB import + scrape JSON fields

**Files:**
- Modify: `app/platforms/facebook/db.py` (`migrate_db`, `import_photos`, `import_reels`, `import_posts`)
- Modify: `app/platforms/facebook/posts_sb.py` (`phase2_scrape_post` and error stub)
- Modify: `app/platforms/facebook/photos_sb.py` (`phase2_scrape_photo` and error stub)
- Modify: `app/platforms/facebook/reels_sb.py` (after comments: `parse_facebook_engagement(sb.get_page_source())`)
- Test: `app/tests/test_facebook_db_counts.py`
- Create: `app/tests/fixtures/fb_about_counts.json`, `app/tests/fixtures/fb_posts_counts.json`

**Interfaces:**
- Consumes: `ensure_engagement_columns`, `as_int`, `parse_facebook_engagement`
- Post JSON includes `like_count`, `reply_count`, `repost_count`
- After `INSERT OR IGNORE`, UPDATE the three columns by post id

- [ ] **Step 1: Failing import test**

`fb_about_counts.json`:

```json
{"profile_url": "https://www.facebook.com/example", "owner_name": "Ex", "is_locked": false, "sections": {}}
```

`fb_posts_counts.json`:

```json
[{"post_url": "https://www.facebook.com/example/posts/1", "date": "2026-08-03", "screenshot_path": null, "comments": [], "like_count": 10, "reply_count": 2, "repost_count": 1}]
```

```python
# app/tests/test_facebook_db_counts.py
import os, sqlite3
from platforms.facebook.db import import_all, init_db

FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')


def test_facebook_import_stores_counts(tmp_path):
    db = str(tmp_path / 'socmint_fb.db')
    init_db(db)
    pid = import_all(
        about_json=os.path.join(FIXTURES, 'fb_about_counts.json'),
        photos_json=os.path.join(FIXTURES, 'missing.json'),
        reels_json=os.path.join(FIXTURES, 'missing.json'),
        posts_json=os.path.join(FIXTURES, 'fb_posts_counts.json'),
        db_file=db,
    )
    assert pid
    con = sqlite3.connect(db)
    row = con.execute(
        'SELECT like_count, reply_count, repost_count FROM text_posts WHERE profile_id=?',
        (pid,),
    ).fetchone()
    con.close()
    assert row == (10, 2, 1)
```

- [ ] **Step 2: Run — expect FAIL** (missing columns or zeros)

- [ ] **Step 3: Implement migrate + UPDATE + scraper merge**

In `migrate_db` after the `text_post_id` block:

```python
    from core.counts import ensure_engagement_columns
    ensure_engagement_columns(con)
```

In `import_posts` after `post_id` is known:

```python
        from core.counts import as_int
        cur.execute(
            '''UPDATE text_posts
               SET like_count=?, reply_count=?, repost_count=?
               WHERE id=?''',
            (as_int(item.get('like_count')), as_int(item.get('reply_count')),
             as_int(item.get('repost_count')), post_id),
        )
```

Same UPDATE for `import_photos` / `import_reels`.

In `phase2_scrape_post` after comments, before return:

```python
    from platforms.facebook.counts_parse import parse_facebook_engagement
    counts = parse_facebook_engagement(sb.get_page_source())
```

Merge `counts` into the returned dict. Exception stubs include `'like_count': 0, 'reply_count': 0, 'repost_count': 0`. Repeat merge in photos/reels scrapers (no All-reactions dialog clicks).

- [ ] **Step 4: Run**

`cd /home/user/tool/birdy-edwards-lite-v2/app && python -m pytest tests/test_facebook_db_counts.py tests/test_facebook_counts_parse.py tests/test_facebook_blueprint.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/platforms/facebook/db.py app/platforms/facebook/posts_sb.py app/platforms/facebook/photos_sb.py app/platforms/facebook/reels_sb.py app/tests/test_facebook_db_counts.py app/tests/fixtures/fb_about_counts.json app/tests/fixtures/fb_posts_counts.json
git commit -m "feat: store Facebook like/comment/repost counts on post rows"
```

---

### Task 5: Instagram counts parse + import

**Files:**
- Modify: `app/platforms/instagram/posts_sb.py` (`parse_post_from_html`)
- Modify: `app/platforms/instagram/reels_sb.py` parse return if it exists as a separate function
- Modify: `app/platforms/instagram/db.py` (`init_db` + import UPDATE)
- Create: `app/tests/fixtures/ig_engagement_snippet.html`
- Test: `app/tests/test_ig_counts_parse.py`

**Interfaces:**
- `parse_post_from_html` adds `like_count`, `reply_count`, `repost_count`
- like ← `"like_count":N` or `edge_media_preview_like`; comment ← `"comment_count":N`; reshare/repost JSON optional else 0
- Accept JSON alias `comment_count` as `reply_count` on import

- [ ] **Step 1: Failing test**

`ig_engagement_snippet.html` contains `"like_count":12` and `"comment_count":3` (not a login page).

```python
# app/tests/test_ig_counts_parse.py
import os
from platforms.instagram.posts_sb import parse_post_from_html

def test_ig_parse_reads_like_and_comment_counts():
    html = open(os.path.join(os.path.dirname(__file__), 'fixtures/ig_engagement_snippet.html'), encoding='utf-8').read()
    got = parse_post_from_html(html, 'https://www.instagram.com/p/AAA/')
    assert got['like_count'] == 12
    assert got['reply_count'] == 3
    assert got['repost_count'] == 0
```

- [ ] **Step 2: Run — FAIL** missing keys
- [ ] **Step 3: Regex JSON ints in `posts_sb.py`; `ensure_engagement_columns` in Instagram `init_db`; UPDATE counts after photo/reel/text insert using `as_int(item.get('like_count') or item.get('comment_count')` only for the matching field — like from `like_count`, reply from `reply_count` or `comment_count`)
- [ ] **Step 4:** `python -m pytest tests/test_ig_counts_parse.py tests/test_ig_db_import.py tests/test_instagram_blueprint.py -v`
- [ ] **Step 5: Commit** `feat: Instagram like/comment/repost count parse and import`

---

### Task 6: Reddit score → like; comment count; repost 0

**Files:**
- Modify: `app/platforms/reddit/submissions_sb.py` (the existing function whose return dict already includes `score` — grep `^def `)
- Modify: `app/platforms/reddit/db.py` (`_ensure_text_post_columns` / `init_db` + `import_submissions` UPDATE)
- Test: `app/tests/test_reddit_counts.py`

**Interfaces:**
- `like_count = score or 0`; `reply_count` from an explicit comment-count field if present else `len(comments)`; `repost_count = 0`

- [ ] **Step 1: Failing import test**

```python
# app/tests/test_reddit_counts.py
import json, os, sqlite3
from platforms.reddit.db import import_all, init_db

def test_reddit_import_maps_score_to_like(tmp_path):
    db = str(tmp_path / 'socmint_reddit.db')
    about = tmp_path / 'reddit_about.json'
    posts = tmp_path / 'reddit_submissions.json'
    about.write_text(json.dumps({
        'profile_url': 'https://www.reddit.com/user/example/',
        'owner_name': 'example', 'is_locked': False, 'sections': {},
    }), encoding='utf-8')
    posts.write_text(json.dumps([{
        'post_url': 'https://www.reddit.com/r/x/comments/abc/t/',
        'date': '2026-08-03', 'title': 't', 'subreddit': 'x', 'body': '',
        'score': 42, 'comments': [{'name': 'a', 'profile_url': 'https://www.reddit.com/user/a/', 'comment_text': 'hi'}],
        'like_count': 42, 'reply_count': 1, 'repost_count': 0,
    }]), encoding='utf-8')
    init_db(db)
    pid = import_all(str(about), str(posts), db)
    row = sqlite3.connect(db).execute(
        'SELECT like_count, reply_count, repost_count FROM text_posts WHERE profile_id=?',
        (pid,),
    ).fetchone()
    assert row == (42, 1, 0)
```

`import_all` signature in `reddit/db.py` may be `import_all(about_json=, submissions_json=, db_file=)` — match that exactly.

Also set the three keys on the scrape return dict (`like_count` from `score`, `reply_count` from `len(comments)`, `repost_count` 0).

- [ ] **Step 2: FAIL** then **Step 3: migrate + UPDATE** **Step 4: pytest** `tests/test_reddit_counts.py` **Step 5: commit** `feat: Reddit like/comment counts on submissions`

---

### Task 7: Threads persist displayed counts on import

**Files:**
- Modify: `app/platforms/threads/db.py`
- Test: extend `app/tests/test_threads_db_import.py`

**Interfaces:**
- `parse_post_from_html` already returns `like_count`, `reply_count`, `repost_count`. Persist them on `text_posts` via `ensure_engagement_columns` + INSERT/UPDATE with `as_int`.

- [ ] **Step 1:** Add assertions to the existing threads import test: after import, `SELECT like_count, reply_count, repost_count FROM text_posts` matches fixture JSON (use `app/tests/fixtures` threads post JSON; if zeros, add counts to that fixture).
- [ ] **Step 2: FAIL** if columns missing
- [ ] **Step 3: migrate + write counts**
- [ ] **Step 4:** `python -m pytest tests/test_threads_db_import.py -v`
- [ ] **Step 5: Commit** `feat: persist Threads like/reply/repost counts on text_posts`

---

### Task 8: Telegram map reactions/forwards onto post columns

**Files:**
- Modify: `app/platforms/telegram/collector.py` (each stored item gets numeric `like_count` / `repost_count` from `_message_engagement`; preview nodes via `parse_compact_int`)
- Modify: `app/platforms/telegram/db.py` migrate + import UPDATE
- Test: `app/tests/test_telegram_counts.py`

**Interfaces:**
- `like_count` ← reaction int; `repost_count` ← forwards int; `reply_count` ← known comment count or 0
- Do not only stuff numbers into `[engagement]` caption text

- [ ] **Step 1:**

```python
# app/tests/test_telegram_counts.py
import json, sqlite3
from platforms.telegram.db import import_all, init_db

def test_telegram_import_stores_like_and_repost(tmp_path):
    db = str(tmp_path / 'socmint_tg.db')
    about = tmp_path / 'tg_about.json'
    posts = tmp_path / 'tg_posts.json'
    about.write_text(json.dumps({
        'profile_url': 'https://t.me/example', 'owner_name': 'Ex',
        'is_locked': False, 'sections': {},
    }), encoding='utf-8')
    # match telegram import_all argument names and JSON filenames used in test_tg_db_import.py
```

Open `app/tests/test_tg_db_import.py` and copy its `import_all(...)` call shape. Write one text post with `like_count: 7, reply_count: 0, repost_count: 2`. Assert SELECT equals `(7, 0, 2)`.

- [ ] **Step 2: FAIL** **Step 3: columns + collector keys + UPDATE** **Step 4: pytest** **Step 5: commit** `feat: Telegram reaction/forward counts as like/repost`

---

### Task 9: APIs — investigations SUM + activity-metrics

**Files:**
- Modify: `app/platforms/facebook/blueprint.py`
- Modify: `app/platforms/instagram/blueprint.py`
- Modify: `app/platforms/reddit/blueprint.py`
- Modify: `app/platforms/threads/blueprint.py`
- Modify: `app/platforms/telegram/blueprint.py`
- Modify: `app/platforms/x/blueprint.py`
- Modify: each platform `api/photo-posts`, `api/text-posts`, `api/reel-posts` SELECT to include the three COALESCE counts (keep `interaction_count` as comment COUNT)
- Test: `app/tests/test_engagement_api.py`

**Interfaces:**
- `GET /{platform}/api/activity-metrics/<int:profile_id>` → `{'ok': True, 'data': get_activity_metrics(DB_FILE, profile_id)}`
- Investigations records add `like_count`, `reply_count`, `repost_count` sums across photo+reel+text
- X already has sums; add the activity-metrics route only if missing

- [ ] **Step 1:**

```python
# app/tests/test_engagement_api.py
import importlib.util, os

def _load_app():
    path = os.path.join(os.path.dirname(__file__), '..', 'app.py')
    spec = importlib.util.spec_from_file_location('birdy_app', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.app

def test_facebook_activity_metrics_ok():
    r = _load_app().test_client().get('/facebook/api/activity-metrics/1')
    assert r.status_code == 200
    body = r.get_json()
    assert 'ok' in body

def test_x_activity_metrics_ok():
    r = _load_app().test_client().get('/x/api/activity-metrics/1')
    assert r.status_code == 200
```

- [ ] **Step 2: FAIL** 404
- [ ] **Step 3:** After each `/api/timeline/` route, register activity-metrics. Import `from core.engagement_metrics import get_activity_metrics`. Add SUM triplets to investigations:

```sql
(SELECT COALESCE(SUM(like_count),0) FROM photo_posts WHERE profile_id=p.id)
+ (SELECT COALESCE(SUM(like_count),0) FROM reel_posts WHERE profile_id=p.id)
+ (SELECT COALESCE(SUM(like_count),0) FROM text_posts WHERE profile_id=p.id) AS like_count
```

Repeat for `reply_count` and `repost_count`. Include keys in the JSON record dict.

- [ ] **Step 4:** `python -m pytest tests/test_engagement_api.py tests/test_facebook_blueprint.py tests/test_instagram_blueprint.py tests/test_reddit_blueprint.py tests/test_threads_blueprint.py tests/test_telegram_blueprint.py -v`
- [ ] **Step 5: Commit** `feat: activity-metrics API and home investigation count sums`

---

### Task 10: Dashboards — home stats, post metrics, Activity Timeline

**Files:**
- Modify: `app/templates/facebook/index.html`, `instagram/index.html`, `reddit/index.html`, `threads/index.html`, `telegram/index.html`; X index: relabel Reply → **Comment**
- Modify: `app/templates/{facebook,instagram,reddit,threads,telegram,x}/analysis.html`
- Test: `app/tests/test_engagement_ui.py`

**Interfaces:**
- Home stats: Comment (`reply_count`), Repost, Like (X keeps View)
- Analysis `statLikes` / `statComments` / `statReposts` from `get_activity_metrics` totals
- Post cards: replace `interaction_count` intrx as the **primary** metric with Comment · Repost · Like (`p.reply_count`, `p.repost_count`, `p.like_count`)
- Activity Timeline card: stacked Like/Comment/Repost; fetch `${PLATFORM_PREFIX}/api/activity-metrics/${PROFILE}`
- Copy `.x-metrics` CSS from `templates/x/analysis.html` and `.metrics-stat-row` from `templates/telegram/analysis.html` if missing
- Copy `fmtCompact` from X analysis if missing

- [ ] **Step 1:**

```python
# app/tests/test_engagement_ui.py
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1] / 'templates'
PLATFORMS = ('facebook', 'instagram', 'reddit', 'threads', 'telegram', 'x')

def test_analysis_has_activity_metrics_and_stat_likes():
    for name in PLATFORMS:
        text = (ROOT / name / 'analysis.html').read_text(encoding='utf-8')
        assert 'activity-metrics' in text, name
        assert 'statLikes' in text, name
```

- [ ] **Step 2: FAIL** then implement.

Day chart (all six analysis pages):

```javascript
activityDayInstance = new Chart(document.getElementById('activityDayChart').getContext('2d'), {
    type: 'bar',
    data: {
        labels: byDate.map(d => d.date),
        datasets: [
            { label: 'Like', data: byDate.map(d => d.like || 0), backgroundColor: '#f91880', stack: 'e' },
            { label: 'Comment', data: byDate.map(d => d.comment || 0), backgroundColor: '#1d9bf0', stack: 'e' },
            { label: 'Repost', data: byDate.map(d => d.repost || 0), backgroundColor: '#00ba7c', stack: 'e' },
        ]
    },
    options: { ...chartDefaults(), scales: { x: { stacked: true }, y: { stacked: true, beginAtZero: true } } }
});
```

Set `statLikes` / `statComments` / `statReposts` from `total_like` / `total_comment` / `total_repost`. Weekday/hour charts use the same three stacked series. X: map reply → comment; do not add View to this chart.

- [ ] **Step 4:** `python -m pytest tests/test_engagement_ui.py tests/test_api_prefixes.py -v`
- [ ] **Step 5: Commit** `feat: show like/comment/repost on all platform dashboards`

---

### Task 11: Reports — all-platform Like / Comment / Repost

**Files:**
- Modify: `app/core/report.py` (`_fetch_posts`, `gather_report_data`, `build_posts`)
- Test: `app/tests/test_facebook_report_counts.py`

**Interfaces:**
- `_fetch_posts` SELECTs `like_count`, `reply_count`, `repost_count`
- `gather_report_data` sets `engagement: {posts, like, comment, repost}` for non-X; X keeps view-capable `_x_engagement_totals`
- `build_posts` line: `Comment {n} · Repost {n} · Like {n}`

- [ ] **Step 1:**

```python
# app/tests/test_facebook_report_counts.py
import os
from platforms.facebook.db import import_all, init_db
from core.report import gather_report_data

FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')

def test_facebook_json_has_engagement(tmp_path):
    db = str(tmp_path / 'socmint_fb.db')
    init_db(db)
    pid = import_all(
        about_json=os.path.join(FIXTURES, 'fb_about_counts.json'),
        photos_json=os.path.join(FIXTURES, 'missing.json'),
        reels_json=os.path.join(FIXTURES, 'missing.json'),
        posts_json=os.path.join(FIXTURES, 'fb_posts_counts.json'),
        db_file=db,
    )
    data = gather_report_data(pid, db, platform='facebook')
    assert data['engagement']['like'] == 10
    assert data['engagement']['comment'] == 2
    assert data['engagement']['repost'] == 1
    assert data['posts']['texts'][0]['like_count'] == 10
```

- [ ] **Step 2: FAIL** `engagement` is None
- [ ] **Step 3:**

```python
def _engagement_totals(posts: dict) -> dict:
    like = comment = repost = 0
    n = 0
    for bucket in ('photos', 'reels', 'texts'):
        for r in posts.get(bucket) or []:
            n += 1
            like += int(r.get('like_count') or 0)
            comment += int(r.get('reply_count') or r.get('comment_count') or 0)
            repost += int(r.get('repost_count') or 0)
    return {'posts': n, 'like': like, 'comment': comment, 'repost': repost}
```

Call for non-X platforms in `gather_report_data`. Keep X `_x_engagement_totals`.

- [ ] **Step 4:** `python -m pytest tests/test_facebook_report_counts.py tests/test_x_report.py -v`
- [ ] **Step 5: Commit** `feat: include like/comment/repost in all-platform reports`

---

### Task 12: Readme operator note

**Files:**
- Modify: `readme.md` (Features + per-platform gather)

- [ ] **Step 1:** Add bullets: all platforms store Like / Comment / Repost by parsing the post page (X.com pattern); named likers/sharers are not collected; FB Share → Repost; Reddit score → Like; Telegram reactions → Like and forwards → Repost; dashboards show home sums, post metrics, Activity Timeline.
- [ ] **Step 2:** Regression:

`cd /home/user/tool/birdy-edwards-lite-v2/app && python -m pytest tests/test_counts.py tests/test_engagement_metrics.py tests/test_facebook_counts_parse.py tests/test_facebook_db_counts.py tests/test_x_posts_parse.py tests/test_x_db_import.py tests/test_x_report.py tests/test_engagement_api.py tests/test_engagement_ui.py -q`

Expected: PASS

- [ ] **Step 3: Commit** `docs: like/comment/repost counts are X-style parses on every platform`

---

## Spec coverage

| Spec item | Task |
|---|---|
| Shared compact-int | 1 |
| Activity metrics payload | 2 |
| Facebook footer parse, no dialogs | 3–4 |
| Instagram like/comment, repost 0 | 5 |
| Reddit score→like, repost 0 | 6 |
| Threads displayed counts | 7 |
| Telegram reactions/forwards | 8 |
| Home SUM + APIs all six | 9 |
| X-style cards + Telegram timeline | 10 |
| Reports | 11 |
| No like/repost actor tables | none added |
| Frequency unchanged | none changed |
| Views X-only | 9–10 |
| Readme | 12 |
