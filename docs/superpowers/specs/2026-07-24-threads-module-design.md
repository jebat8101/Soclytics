# Threads Module — Design Spec

**Date:** 2026-07-24  
**Project:** birdy-edwards-lite  
**Status:** Approved for implementation planning  

## Goal

Add **Meta Threads** as a fourth SOCMINT mini-app alongside Facebook, Instagram, and Reddit — full lite pipeline (gather → DB → frequency → graphs → faces where images exist), with **separate like / repost / reply counters**.

## Non-goals (v1)

- Official Threads / Instagram Graph API  
- Shared Meta SSO with Instagram cookies (own `threads_cookies.pkl` only)  
- Combined IG+Threads investigations  
- DMs, search, hashtags as targets  
- Changing Facebook / Instagram / Reddit frequency schemas  

## Decisions (locked)

| Topic | Choice |
|---|---|
| Pipeline | Profile/about + posts/threads + replies/likers/reposters → DB → frequency → graphs → faces |
| Scoring | Separate `like_count`, `repost_count`, `reply_count`, `total_count` (sum) |
| UX | Separate mini-app tab (same as IG/Reddit) |
| Auth | Operator cookies + SeleniumBase |
| Targets | Profile only (`threads.net/@user`) |
| Code structure | Clone Instagram package pattern → `platforms/threads/` |

## Architecture

```
app/platforms/threads/
  constants.py      # COOKIE_FILE, DB_FILE, DEPTH_LIMITS, PIPELINE_STEPS, FACE_DIR
  about_sb.py
  posts_sb.py       # posts + harvest replies/likes/reposts
  db.py
  blueprint.py
app/templates/threads/
  index.html, analysis.html
```

| Piece | Value |
|---|---|
| URL prefix | `/threads` |
| Cookie file | `threads_cookies.pkl` |
| Database | `socmint_threads.db` |
| Face dir | `face_data_threads/` |
| Shell tab | Facebook \| Instagram \| Reddit \| **Threads** |

Register blueprint + `init_db` in `app.py`. Reuse `core/` (pipeline, browser, paths, face with `face_dir=`, urls normalizer).

## Gatherers & data model

### Target normalization

- Accept: `@user`, `user`, `https://www.threads.net/@user`, `https://threads.net/@user/`  
- Canonical: `https://www.threads.net/@<user>/`  
- Reject: individual post URLs, search, empty  

### Pipeline steps

1. About / profile  
2. Posts/threads (+ media URLs)  
3. Per-post engagements: replies, likes, reposts  
4. DB import  
5. Frequency scoring  
6. Top-N about enrichment  
7. Face clustering (images only)  
8. Finish  

Depth presets map to post caps (and optional per-post engagement caps).

### Artifacts

| Artifact | Contents |
|---|---|
| About | display name, username, bio, website/link, follower/following counts, is_private → `sections` for `profile_fields` |
| Posts | post URL, text/body, date, image_src / media_type |
| Replies | author name, profile URL, comment text → reply engagements |
| Likes | liker name, profile URL (no text) |
| Reposts | reposter name, profile URL |

### Schema (Threads DB)

Keep shared shapes where possible (`profiles`, `profile_fields`, `photo_posts` or `text_posts` for thread posts with optional image, `commentors`).

Engagement tables (or typed rows):

- `thread_replies` (post_id, commentor_id, comment_text)  
- `thread_likes` (post_id, commentor_id) UNIQUE  
- `thread_reposts` (post_id, commentor_id) UNIQUE  

`commentor_frequency` for Threads:

```
like_count, repost_count, reply_count, total_count
```

`total_count = like_count + repost_count + reply_count`.  
Facebook/Instagram/Reddit frequency tables remain unchanged.

### Analysis mapping

- Interactors table: four count columns + total  
- Graphs: edge weight = `total_count`  
- Timeline / donut: by post media type where available  
- Faces: `run_face_clustering(..., face_dir=FACE_DIR)` on posts with `image_src`  

## UI

- Home: cookie import/verify (`threads.net`), start investigation, pipeline status, history/delete  
- Analysis: prefixed `/threads/api/...` routes; no bare `/api/`  
- Placeholders and copy Threads-specific (not FB leftovers)  

## Error handling

- Per-step `active` / `done` / `error`; sibling scrapers continue  
- DB import failure aborts analysis steps  
- Cookie verify fail-closed (including Selenium missing)  
- Locked/private: store visible data, set `is_locked`, don’t hang  
- About import uses `expected_profile_url` to avoid top-N overwrite identity bugs  
- Media routes use `core.paths.safe_under`  

## Testing

- Unit: URL normalizer; fixture import → frequency (like/repost/reply counts); API prefix test for templates  
- Blueprint: home 200; reject post URL start-pipeline 400  
- Live smoke optional when operator provides `threads_cookies.pkl`  

## Security & compliance

Same authorized-use disclaimer as other platforms; operator session; publicly visible data only.

## Implementation order

1. `core/urls.py` — `normalize_threads_target`  
2. `platforms/threads` DB + fixtures + frequency with four counters  
3. Scrapers (about, posts+engagements) with parse helpers + HTML fixtures  
4. Blueprint + templates + shell tab + `app.py` register  
5. Readme + API prefix tests + regression suite  

Detailed tasks belong in the implementation plan after spec approval.
