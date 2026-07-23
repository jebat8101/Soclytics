# Instagram & Reddit Modules — Design Spec

**Date:** 2026-07-23  
**Project:** birdy-edwards-lite  
**Status:** Approved for implementation planning  

## Goal

Add Instagram and Reddit as first-class SOCMINT modules in Birdy-Edwards Lite with **full Facebook-parity pipeline** (gather → DB → frequency → graphs / faces where applicable), while keeping each platform a **separate mini-app** (own cookies, own DB, own investigation history).

Refactor the flat Facebook-only layout into **platform packages + shared core** so Facebook, Instagram, and Reddit plug in the same way.

## Non-goals (v1)

- Official Instagram Graph API or Reddit API (`praw`) — v1 is cookie + SeleniumBase only
- Multi-platform combined investigations (one case spanning FB + IG + Reddit)
- Instagram Stories, hashtags, or locations as targets
- Reddit subreddits or search queries as targets
- Porting these modules to the full (LLM) Birdy-Edwards repo in this workstream
- AI / LLM analysis (lite remains zero-LLM)

## Decisions (locked)

| Topic | Choice |
|---|---|
| Pipeline depth | Full lite parity (Approach A) |
| UX model | Separate mini-apps / tabs (Approach C) |
| Auth | Operator cookies + SeleniumBase, same pattern as Facebook |
| Targets | Profile/user only (IG profile URL or username; Reddit `/user/<name>`) |
| Code structure | Platform packages + shared core (Approach 3) |

## Architecture

```
app/
  core/
    browser.py       # SB + Xvfb bootstrap, cookie load / verify helpers
    pipeline.py      # shared step state (active / done / error)
    scoring.py       # frequency scoring + top-N (from commentor_scoring_lite)
    face.py          # face clustering (from face_intelligence_lite)
    db_base.py       # shared SQLite helpers / common schema pieces
  platforms/
    facebook/        # existing FB scrapers, DB, blueprint, templates
    instagram/       # new IG scrapers, DB, blueprint, templates
    reddit/          # new Reddit scrapers, DB, blueprint, templates
  templates/
    _shell.html      # shared chrome + platform tabs
    facebook/
    instagram/
    reddit/
  app.py             # thin Flask app: register blueprints only
```

### Blueprint namespaces

| Platform | URL prefix | Cookie file | Database |
|---|---|---|---|
| Facebook | `/facebook` | `fb_cookies.pkl` | `socmint_fb.db` |
| Instagram | `/instagram` | `ig_cookies.pkl` | `socmint_ig.db` |
| Reddit | `/reddit` | `reddit_cookies.pkl` | `socmint_reddit.db` |

- `/` redirects to `/facebook` for backward compatibility.
- Each blueprint owns: cookie import/verify, start pipeline, pipeline status, investigation list/delete, analysis APIs, static analysis templates.

### Shared core responsibilities

- **browser:** create SB session, optional Xvfb, load pickle cookies for a given domain, refresh/verify logged-in state
- **pipeline:** in-memory (or small status file) step tracker per platform run; no cross-platform shared run state
- **scoring:** compute interaction frequency and top-N from a platform DB that follows the shared commentor/post/comment shape
- **face:** cluster faces for platforms that download images (Facebook, Instagram); Reddit skips this step
- **db_base:** connection helpers, common table patterns (profiles, commentors, comments, frequency)

Platform packages own site-specific selectors, URLs, JSON shapes, and import mappings.

## Per-platform gatherers & data model

### Common pipeline steps

1. About / profile fields  
2. Content scrapers (parallel, staggered like current FB)  
3. DB import  
4. Frequency scoring  
5. Top-N enrichment (about scrape for top interactors where the platform supports public about)  
6. Face clustering (**Facebook + Instagram only**)  
7. Finish  

Depth presets (shallow / medium / deep) map to per-platform caps (posts, reels/media, comments-per-post as applicable).

### Facebook (existing → moved)

- Scrapers: about, photos, reels, text posts (current `fb_*_sb.py`)
- Schema: current lite schema, DB file renamed `socmint_lite.db` → `socmint_fb.db`
- Analysis: frequency, top7 about, faces, network/co-interactor graphs, timeline, donut — unchanged behavior

### Instagram

| Artifact | Contents |
|---|---|
| About | display name, username, bio, website, follower/following/post counts, is_private |
| Posts | post URL, caption, date, image/video thumb src, media type |
| Reels | reel URL, caption/date where available |
| Comments | commentor username + profile URL + comment text, linked to post/reel |
| Skip (v1) | Stories, DMs, highlights-as-targets |

- Faces: run on downloaded post/reel images when available  
- Top-N: scrape public profile about for top interactors when profiles are visible  

### Reddit

| Artifact | Contents |
|---|---|
| About | username, karma (post/comment if visible), cake day, public profile fields |
| Submissions | post URL, title, subreddit, date, selftext/link, score if visible |
| Comments on those submissions | comment author + profile URL + body |
| Skip (v1) | subreddit targets, search, private messages, face step |

- Graphs/frequency: treat comment authors as interactors on the target user’s submissions  
- No face clustering step in the Reddit pipeline UI or runner  

### Target normalization

- Instagram: accept `https://www.instagram.com/<user>/` or bare `@user` / `user` → normalize to profile URL  
- Reddit: accept `https://www.reddit.com/user/<name>/` or `u/<name>` → normalize to `/user/<name>`  
- Reject non-profile URLs with a clear validation error before the pipeline starts  

## UI

- Shared shell with tabs: **Facebook | Instagram | Reddit**
- Per mini-app home:
  - Cookie import + verify session
  - Start investigation (target + depth)
  - Live pipeline step list (platform-specific steps; Reddit omits face)
  - Investigation history with delete (DB rows + downloaded face/media files for that platform)
- Analysis dashboard: reuse existing chart/graph patterns; hide face cluster UI on Reddit; map IG media to photo/reel/text-style views

## Migration

1. Introduce `core/` and `platforms/facebook/` without changing FB behavior.  
2. Move FB scrapers, DB module, scoring/face imports, and templates under the Facebook blueprint.  
3. On startup (or one-shot migrate): if `socmint_lite.db` exists and `socmint_fb.db` does not, rename/copy to `socmint_fb.db`.  
4. Keep `fb_cookies.pkl` path stable so existing sessions still work.  
5. Add Instagram and Reddit packages afterward (scrapers → DB → blueprint → UI).  

Existing Facebook investigations must remain openable after migration.

## Error handling

- Per-step `active` / `done` / `error`; failed content scrapers do not cancel sibling scrapers.  
- DB import failure aborts frequency / top-N / face steps and finishes the pipeline with an error message.  
- Cookie/session verify fails closed; scrapers exit non-zero if not authenticated.  
- Locked/private profiles: set `is_locked` (or platform equivalent), store whatever public fields/posts were visible, do not hang.  
- Cookie import validates JSON/pickle structure and required domains (`.instagram.com`, `.reddit.com`, `.facebook.com`) before writing the platform cookie file.

## Testing (implementation plan will detail)

- Unit: URL normalizers; schema create; import from fixture JSON  
- Integration (manual / optional CI): cookie verify dry-run; one shallow scrape per platform against a known public test account the operator authorizes  
- Regression: Facebook home → pipeline status → open existing investigation after restructure  

## Security & compliance notes

Same disclaimer as current lite: authorized use only; operator-supplied session; publicly visible data only; no fake-account creation. New modules must not scrape private messages or locked content beyond what the operator’s session can already see.

## Implementation order (high level)

1. Extract `core/` + move Facebook into `platforms/facebook/` + DB rename migration  
2. Instagram package: scrapers, DB, blueprint, UI tab  
3. Reddit package: scrapers, DB, blueprint, UI tab  
4. Wire shared scoring/graphs; enable face for IG only  
5. Regression pass on Facebook; shallow E2E smoke on IG + Reddit  

Detailed task breakdown belongs in the implementation plan (next step after spec approval).
