# Telegram Text Modules — Design Spec

**Date:** 2026-08-06  
**Project:** birdy-edwards-lite-v2  
**Status:** Approved for implementation planning  

## Goal

Add three ConvoMetrics-style text intelligence modules to the **Telegram** analysis page:

1. **Activity Timeline** — message/post volume over time  
2. **Word Analysis** — stopword-filtered top words + word cloud  
3. **Word Searcher** — who said a word, when, with snippets  

Corpus covers scraped channel/profile posts + comments, plus an optional Telegram Desktop chat-export (`result.json`) upload merged into the same investigation.

## Non-goals (v1)

- Porting modules to Facebook / Instagram / Reddit / Threads UI (shared core only)  
- WhatsApp export parsing  
- Emoji Usage tab from ConvoMetrics  
- LLM / embedding topic models  
- Changing existing interactor / network / face cards  
- Replacing the existing Interaction Frequency timeline (that stays; Activity Timeline is content-volume, not interaction-volume)

## Decisions (locked)

| Topic | Choice |
|---|---|
| Approach | Shared `core/text_analytics.py` + Telegram APIs + analysis cards |
| UI placement | New cards on existing `/telegram/analysis` grid (not separate tabs/page) |
| Corpus | Posts + comments + optional chat-export upload |
| Charts | Chart.js (match analysis page) |
| Word cloud | Server-side PNG via `wordcloud` |
| Stopwords | NLTK English + chat artifacts; built-in fallback if NLTK data missing |
| Search match | Exact token after lowercasing + punctuation strip (ConvoMetrics) |
| Upload limit | Reject JSON > 25MB |

## Architecture

```
app/core/text_analytics.py          # corpus + aggregates + cloud + export parse
app/platforms/telegram/blueprint.py # new API routes
app/templates/telegram/analysis.html # three new cards + JS
app/chat_exports/<profile_id>/      # stored result.json per investigation
app/tests/test_text_analytics.py
app/tests/test_telegram_text_apis.py
```

Telegram blueprint loads scraped rows from `socmint_tg.db`, builds a normalized message list via `core.text_analytics`, merges any stored export, returns JSON for the cards.

### Normalized message record

```python
{
  "timestamp": "2026-08-05T14:22:00",  # ISO when possible; date-only OK
  "date": "2026-08-05",
  "hour": 14,                          # None if unknown
  "sender": "Middle_East_Spectator",   # owner, commentor name, or export "from"
  "message": "plain text body",
  "source": "photo_caption" | "text_post" | "comment" | "chat_export",
}
```

## Corpus builders

### From scrape DB (always)

| Source | Text | Sender | Timestamp |
|---|---|---|---|
| `photo_posts.caption` | Caption with `[engagement] …` footer stripped | Profile `owner_name` | `date_text` |
| `text_posts` via `screenshot_path` `.txt` | File body, engagement footer stripped; skip if file missing | Profile `owner_name` | `date_text` |
| `photo_comments` / `reel_comments` / `text_comments` | `comment_text` | Commentor `name` | Parent post `date_text` (best available) |

Reel captions are included only if present in DB/JSON import path already used by Telegram; no new reel schema required for v1.

### From optional chat export

- `POST` multipart upload of Telegram Desktop **Machine-readable JSON** (`result.json`)  
- Parse `messages[]` where `type == "message"` and `from` exists (same rules as ConvoMetrics)  
- Flatten list-form `text` entities to a string  
- Store at `app/chat_exports/<profile_id>/result.json` (overwrite on re-upload)  
- Merge into corpus for all text APIs for that `profile_id`

## APIs

| Method | Path | Purpose |
|---|---|---|
| GET | `/telegram/api/text-activity/<profile_id>` | Daily counts, day-of-week, hour-of-day |
| GET | `/telegram/api/word-analysis/<profile_id>?sender=&top=30` | Top words; `senders` list for filter |
| GET | `/telegram/api/word-cloud/<profile_id>?sender=` | PNG word cloud |
| GET | `/telegram/api/word-search/<profile_id>?q=` | Total, by-sender, by-date, snippets (cap ~50) |
| POST | `/telegram/api/chat-export/<profile_id>` | Upload/replace export JSON |
| GET | `/telegram/api/chat-export/<profile_id>` | Status: whether export present + message count |
| DELETE | `/telegram/api/chat-export/<profile_id>` | Remove stored export |

All success payloads use `{ok: true, ...}`. Empty corpus returns empty series/lists, not errors.

## UI cards (analysis grid)

Place below existing post galleries, matching card chrome (`card-title`, `card-meta`, Chart.js):

1. **Activity Timeline** (`span-12` or `span-8`+sidebar)  
   - Line: messages per day  
   - Bar: busiest weekday  
   - Bar: activity by hour (hide or empty-state if no hour data)

2. **Word Analysis** (`span-6` or `span-12`)  
   - Sender `<select>` (All + distinct senders)  
   - Horizontal bar: top words  
   - Word-cloud `<img>` from cloud endpoint  
   - Small upload control for chat export + status chip

3. **Word Searcher** (`span-6` or `span-12`)  
   - Search input + button  
   - Total hit count  
   - Pie: who said it  
   - Line: usage over time  
   - Snippet list (sender · date · excerpt)

Chat-export upload may live once in the Word Analysis card header (shared state for all three cards via reload of corpus-backed endpoints).

## Error handling

- Missing/unknown `profile_id` → 404 JSON  
- Empty corpus → empty-state UI copy: `NO TEXT TO ANALYZE`  
- Invalid export JSON / not Telegram shape → 400, prior file kept  
- Oversized upload (>25MB) → 400  
- Missing text-post screenshot file → skip message, continue  
- NLTK stopwords unavailable → built-in English stopword set + chat artifacts  
- Empty search query → 400  

## Dependencies

Add to setup / venv install notes:

- `nltk`  
- `wordcloud`  

On first use, attempt `nltk.download("stopwords", quiet=True)`; never fail the request if download is blocked.

## Testing

- Unit: caption footer strip; text-file load; comment attribution; Telegram export parse (string + list text)  
- Unit: activity buckets; top-words excludes stopwords; search exact-token counts  
- Blueprint smoke: each new route with a fixture profile (or in-memory temp DB + sample files)  

## Out of scope follow-ups

- Surface same cards on other platforms using `core/text_analytics`  
- Persist export inside SQLite instead of filesystem  
- Multilingual stopwords beyond English  
