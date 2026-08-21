# Soclytics Features

Local-first multi-platform SOCMINT. No LLM. No official social APIs.

---

## Platforms

- **Facebook** — about, photos, reels, posts + comments; face clustering
- **Instagram** — about, posts, reels + comments; face clustering
- **Reddit** — about, submissions + comments; **no** face step
- **Threads** — about, posts across tabs; face clustering
- **Telegram** — posts/media + interactors (MTProto or public preview)
- **X** — posts + counts; **Views (X-only)**; face clustering

Each platform has its own cookies/session, SQLite DB, and investigation history.

---

## Collection

- Profile-only targets (URL / `@handle` / bare name where supported)
- Operator auth: Cookie-Editor (FB/IG/Reddit/Threads/X) or Telethon (Telegram)
- **Scan depth:** Light / Medium / **Deep (unlimited)** until scroll idle
- **Optional date range:** From / To filter after collection
- Live pipeline progress overlay
- SeleniumBase (browser platforms); Telethon or `t.me/s` (Telegram)

---

## Engagement & scoring

- Like / Comment / Repost counts (platform-parsed)
- Views on **X only**
- Frequency scoring of interactors
- Top 7 priority targets + about cards
- Interactor registry / apex interactor

---

## Analysis dashboard

- Network graph (target ↔ interactors, fullscreen)
- Co-interactor matrix (1+ / 2+ / 3+ / 5+)
- Co-interactor force graph
- Interaction timeline (date-stacked)
- Distribution donut (content type)
- Post/media cards with engagement metrics
- Dark / light theme

---

## Face intelligence

- CNN / HOG detection + clustering
- Face cluster tree
- Platforms: **Facebook, Instagram, Threads** (and Telegram/X where the face step is in the pipeline); **not Reddit**

---

## Reports & ops

- **PDF** full intelligence report
- **JSON** export
- Investigation list + delete (purge local data)
- Cookie/session import + verify
- Fully local — no cloud, no GPU required for core flow

---

## What it does *not* do

- No DMs / private / locked content beyond the operator session
- No official Graph API / Twitter API / PRAW
- No LLM sentiment / emotion / country AI (Lite edition)
- Date range is **filter after scrape**, not true scroll-until-date

---

## Capability matrix

| Feature | FB | IG | Reddit | Threads | Telegram | X |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| Profile gather | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Depth + date range | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Deep unlimited | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Engagement counts | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Views | — | — | — | — | — | ✅ |
| Face clustering | ✅ | ✅ | — | ✅ | ✅* | ✅* |
| Network / co-graph | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| PDF / JSON report | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

\*where face step is in that platform’s pipeline
