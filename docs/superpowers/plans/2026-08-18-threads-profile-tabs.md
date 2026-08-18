# Threads Profile Tabs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scrape a Threads profile in native tab order — Threads, Replies, Media, Reposts — and keep people who replied on the target’s own posts.

**Architecture:** Collect post URLs from each profile tab URL (`/@user/`, `/replies/`, `/media/`, `/reposts/`), tag each URL with `source_tab`, dedupe (first tab wins). Own-authored posts get full reply harvest (username + comment text). Other authors (typical Reposts tab) store the post and counts only.

**Tech Stack:** SeleniumBase `posts_sb.py`, SQLite `text_posts.source_tab`, Flask analysis dashboard tabs.

## Global Constraints

- Threads Deep remains unlimited own-tab collection (`DEPTH_LIMITS['deep']['posts'] is None`).
- Light = 5 total unique posts, Medium = 10, filled in tab order.
- No liker/reposter actor lists beyond existing activity-dialog harvest on own posts.
- Do not scrape Followers/Following lists.

---

### Task 1: Tab URL + merge helpers

**Files:**
- Modify: `app/platforms/threads/posts_sb.py`
- Test: `app/tests/test_threads_posts_parse.py`

**Interfaces:**
- Produces: `PROFILE_TABS`, `profile_tab_url(profile_url, tab) -> str`, `merge_tab_urls(by_tab, profile_url, cap=None) -> list[dict]`, `is_own_post(post_url, profile_url) -> bool`

- [ ] **Step 1: Write failing tests** for `profile_tab_url` and `merge_tab_urls`
- [ ] **Step 2: Implement helpers**
- [ ] **Step 3: Run** `cd app && python -m pytest -p no:seleniumbase tests/test_threads_posts_parse.py -q`

---

### Task 2: Collect from all four tabs

**Files:**
- Modify: `app/platforms/threads/posts_sb.py` (`phase1_collect_urls`, `main`, `phase2_scrape_post`)

**Interfaces:**
- Consumes: Task 1 helpers
- Produces: `phase1_collect_urls` returns `[{'post_url', 'source_tab'}, ...]`; JSON items include `source_tab`; own posts expand replies, others skip expand

- [ ] **Step 1: Visit each tab URL, collect_until_idle, merge_tab_urls**
- [ ] **Step 2: phase2 harvest replies only when `is_own_post`**
- [ ] **Step 3: Attach `source_tab` on each result**

---

### Task 3: Persist `source_tab`

**Files:**
- Modify: `app/platforms/threads/db.py`
- Test: `app/tests/test_threads_db_import.py`

**Interfaces:**
- Produces: `ensure_source_tab_column(con)`; `text_posts.source_tab` TEXT default `'threads'`

- [ ] **Step 1: Failing import test** that `source_tab='replies'` is stored
- [ ] **Step 2: ALTER + UPDATE on import**
- [ ] **Step 3: API SELECT includes `source_tab`** (`blueprint.py` text/photo/reel endpoints)

---

### Task 4: Dashboard tabs matching Threads UI

**Files:**
- Modify: `app/templates/threads/analysis.html`
- Modify: `app/templates/threads/index.html` Deep label

**Interfaces:**
- Consumes: `source_tab` from `/threads/api/text-posts/<id>`
- Produces: Threads | Replies | Media | Reposts filter on the post feed

- [ ] **Step 1: Tab bar filters `textPosts`**
- [ ] **Step 2: Deep home copy = native tab names**
