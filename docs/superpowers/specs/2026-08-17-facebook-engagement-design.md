# All-Platform Engagement Counts (X.com scrape pattern) — Design Spec

**Date:** 2026-08-17 (revised)  
**Project:** birdy-edwards-lite-v2  
**Status:** Ready for review  

This spec **replaces** the earlier Facebook-dialog / named-reactor design.

## Goal

Every mini-app (**Facebook, Instagram, Reddit, Threads, Telegram, X**) scrapes **Like / Comment / Repost counts the way X.com already does**, shows those counts on the home list and analysis dashboard, and writes them into PDF/JSON. Analysis also gets a Telegram-style **Activity Timeline** stacked as those three series.

X module rules to copy (`platforms/x/posts_sb.py`, `platforms/x/db.py`):

- Parse compact integers from visible labels / aria-text / embedded JSON (`12`, `1.2K`).
- Store `like_count`, `reply_count` (comment), `repost_count` on the post row.
- **No actor lists** for likes or reposts.
- Fixture HTML + `parse_*_from_html` unit tests (see `app/tests/test_x_posts_parse.py`).
- Home investigations query `SUM` of the three counts.
- Analysis post cards use the X metrics row (Like · Comment · Repost). X keeps **View** as a fourth, X-only, number.

Existing **comment people** harvest (FB / IG / Reddit / Threads / Telegram) stays. This spec does **not** open Facebook reaction/share dialogs or Instagram like-lists.

## Non-goals

- Official platform APIs  
- Named likers / reactors / sharers / reposters  
- Per-emoji Facebook breakdown in charts (one Like number = total reactions)  
- Telegram Word Analysis copied onto other tabs  
- Re-scraping old investigations automatically  
- Changing cookie/auth flow  
- Reddit crosspost people; Instagram send-to people  

## Decisions (locked)

| Topic | Choice |
|---|---|
| Platforms that **output** counts | All six: facebook, instagram, reddit, threads, telegram, x |
| Scrape style | Clone X: HTML/JSON count parse + fixtures; no like/repost actor lists |
| Dashboard labels | **Like / Comment / Repost** (X Reply → Comment; FB Share → Repost; TG Forward → Repost; Reddit score → Like) |
| Visualization | X-style post metrics **and** Telegram Activity Timeline (day / weekday / hour, stacked three series) |
| Views | X only |
| Frequency / graphs | Unchanged for comment interactors. Do not add likers into Top 7 |

### Native mapping

| Series | Facebook | Instagram | Reddit | Threads | Telegram | X |
|---|---|---|---|---|---|---|
| Like | Total reactions on the footer | Like count | Submission score | Like count | Reaction count | Like count |
| Comment | Comment count | Comment count | Comment count | Reply count | Comment / reply count | Reply count |
| Repost | Share count | Public repost count or 0 | 0 | Repost count | Forwards | Repost count |

API keys everywhere: `like`, `comment`, `repost` (X also `view`).

## Architecture

```
core/engagement_metrics.py     # shared activity-metrics from post dates + counts
platforms/x/posts_sb.py        # reference implementation (already shipped)
platforms/{fb,ig,reddit,threads,telegram} scrape:
  parse_*_from_html()          # counts; fixture-tested like X
  store like_count / comment-or-reply_count / repost_count on post rows
templates/*/index.html         # investigation list: Like / Comment / Repost sums (X already does)
templates/*/analysis.html      # post metrics row + Activity Timeline
core/report.py                 # generalize X post-metrics inventory to all platforms
```

Do **not** add `{photo,reel,text}_reactions` or `_shares` people tables.

Shared:

`GET /{platform}/api/activity-metrics/<profile_id>`

```json
{
  "total_like": 0,
  "total_comment": 0,
  "total_repost": 0,
  "by_date": [{"date": "2026-08-01", "like": 0, "comment": 0, "repost": 0}],
  "by_weekday": [{"day": "Monday", "like": 0, "comment": 0, "repost": 0}],
  "by_hour": [{"hour": 0, "like": 0, "comment": 0, "repost": 0}],
  "has_hour_data": false
}
```

X may include `view` in `by_date` without putting views on other platforms.

Missing hour on a post → `has_hour_data` false (Telegram behavior).

## Scrape (per platform, X pattern)

Each gatherer, after it already collects a post URL, parses counts from that page’s HTML/JSON:

1. Compact-int helper (reuse `_parse_compact_int` from X or a thin `core/counts.py` copy used by all).  
2. Label regex / aria / data-testid / JSON keys appropriate to the site.  
3. `parse_*_from_html(html, url) -> {like_count, comment_count|reply_count, repost_count, date, ...}`.  
4. Fixture file under `app/tests/fixtures/` + pytest.  
5. Import writes counts onto `photo_posts` / `reel_posts` / `text_posts` (`migrate_db` adds columns).  

If a number is absent, store 0. Do not substitute `COUNT(*)` of comments into `like_count` / `repost_count`. Comment **count** on the post row is the **displayed** number (X `reply_count` pattern), which may exceed harvested commenter rows.

**Facebook:** parse the post footer (reactions total, comments, shares). Do not click All reactions / Shares.

**Instagram:** parse like / comment counts from the post; repost = 0 unless a public number exists.

**Reddit:** map existing `score` → `like_count`; comment count from listing/post; `repost_count = 0`.

**Threads:** persist displayed like / reply / repost numbers already present in parse (do not require activity-dialog people for this feature). Dialog people already collected stay as-is.

**Telegram:** map reactions → like, comments → comment, forwards → repost on each stored message/post. Preview vs MTProto can fill what is visible.

**X:** already complete; wire Activity Timeline next to existing metrics (Reply shown as Comment in the three-series chart; keep View on the post card).

## Dashboard

**Home (all platforms):** investigation cards/rows show Like / Comment / Repost totals (`SUM` of post columns), matching X `get_investigations`.

**Analysis header:** Posts, Interactors, Faces stay. Add Likes / Comments / Reposts (displayed sums). X also Views.

**Post cards:** replace primary “intrx” with the X metrics row: Comment · Repost · Like (Facebook/IG/Reddit/Threads/Telegram). Harvested commenter count can remain secondary if useful.

**Activity Timeline card** (Telegram layout): stats Likes / Comments / Reposts; charts stacked three series.

## Reports

Generalize X’s per-post Reply / Repost / Like block to all platforms (`comment` / `repost` / `like`). Summary totals from `SUM`. Telegram / X extra sections (word cloud, views) stay. Do not drop existing comment samples.

## Error handling

- Parse miss → 0, continue post.  
- One post failing counts does not abort gather.  
- Missing columns on old DBs → metrics return 0 (`migrate_db` + COALESCE).  
- Instagram/Reddit with no repost UI → `repost` 0 is success.

## Testing

- Per-platform `parse_*_from_html` fixtures (Facebook footer, IG like/comment, Reddit score, Threads counts, Telegram reactions/forwards, X already exists).  
- Import fixture JSON → DB columns → `SUM` and `activity-metrics` stacks.  
- Old JSON without count keys still imports (zeros).  
- X report tests still pass; add one Facebook + one Reddit report JSON assertion for the three keys.  
- Blueprint: each platform home 200; investigations payload includes the three sums.

## Security & compliance

Operator cookies / Telegram keys as today; publicly visible counts only; no official APIs.

## Implementation order

1. Shared compact-int + `core/engagement_metrics.py` + tests.  
2. Schema migrate `like_count` / `reply_count` or `comment_count` / `repost_count` on post tables for FB, IG, Reddit, Threads, Telegram.  
3. Parsers + fixtures per platform (Facebook first, then IG, Reddit, Telegram; Threads persist displayed counts).  
4. Home investigations + analysis metrics row + Activity Timeline on all six templates.  
5. `core/report.py` all-platform inventory.  
6. Readme: counts are X-style parses, not actor lists.

Detailed tasks belong in the implementation plan after spec approval.
