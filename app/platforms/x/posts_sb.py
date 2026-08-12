"""X.com posts scraper via SeleniumBase.

Collects profile status URLs, then per tweet scrapes caption / date / media
and numeric reply / repost / like / view counts. No actor lists.
"""
import json
import os
import re
import subprocess
import time
from html import unescape
from urllib.parse import urlparse

from seleniumbase import SB

from platforms.x.about_sb import _looks_like_login_page, _require_cookies, login

if os.name != 'nt':
    try:
        os.environ.setdefault('DISPLAY', ':99')
        subprocess.Popen(
            ['Xvfb', ':99', '-screen', '0', '1920x1080x24'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(1)
    except FileNotFoundError:
        pass

OUTPUT_FILE = 'x_posts.json'

_STATUS_RE = re.compile(
    r'(?:https?://(?:www\.)?(?:x|twitter)\.com)?/([A-Za-z0-9_]+)/status/(\d+)',
    re.I,
)
_COUNT_LABEL = re.compile(
    r'(\d[\d,]*(?:\.\d+)?)\s*([KMB])?\s*(Repl(?:y|ies)|Reposts?|Likes?|Views?|Bookmarks?)',
    re.I,
)


def _parse_compact_int(num: str, suffix: str | None = None) -> int | None:
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


def _handle_from_url(profile_url: str) -> str:
    path = urlparse(profile_url).path.strip('/')
    first = (path.split('/')[0] if path else '').lstrip('@')
    return first


def _clean_status_url(href: str, handle: str | None = None) -> str | None:
    if not href:
        return None
    href = href.split('?')[0].split('#')[0]
    low = href.lower()
    if '/analytics' in low or '/photo/' in low or '/quotes' in low or '/retweets' in low:
        return None
    match = _STATUS_RE.search(href)
    if not match:
        return None
    user, tid = match.group(1), match.group(2)
    rest = href.split(f'/status/{tid}', 1)[-1]
    if rest and rest not in ('/',) and not rest.startswith('?'):
        return None
    if handle and user.lower() != handle.lower():
        return None
    return f'https://x.com/{user}/status/{tid}'


_ARTICLE_BLOCK_RE = re.compile(
    r'<article[^>]*data-testid=["\']tweet["\'][^>]*>([\s\S]*?)</article>',
    re.I,
)
_PINNED_CONTEXT_RE = re.compile(
    r'data-testid=["\']socialContext["\'][\s\S]{0,800}?(Pinned|Pin to profile|Pinned Post)',
    re.I,
)
_PINNED_ID_LIST_RE = re.compile(
    r'"(?:pinned_tweet_ids_str|pinned_tweet_ids|pinnedTweetIds)"\s*:\s*\[(.*?)\]',
    re.I | re.S,
)
_PINNED_ID_ONE_RE = re.compile(
    r'"(?:pinned_tweet_id_str|pinnedTweetId)"\s*:\s*"(\d+)"',
    re.I,
)


def status_id_from_url(url: str | None) -> str | None:
    if not url:
        return None
    match = _STATUS_RE.search(url)
    return match.group(2) if match else None


def pinned_tweet_ids_from_html(html: str) -> set[str]:
    """IDs from X user JSON (pinned_tweet_ids_str) — works even when the UI is icon-only."""
    ids: set[str] = set()
    for match in _PINNED_ID_LIST_RE.finditer(html or ''):
        ids.update(re.findall(r'\d{5,}', match.group(1)))
    for match in _PINNED_ID_ONE_RE.finditer(html or ''):
        ids.add(match.group(1))
    return ids


def _article_html_is_pinned(block: str) -> bool:
    if not block:
        return False
    if _PINNED_CONTEXT_RE.search(block):
        return True
    if re.search(r'aria-label=["\'][^"\']*pin(?:ned)?[^"\']*["\']', block, re.I):
        if not re.search(r'aria-label=["\'][^"\']*(spin|pink|pinpoint)[^"\']*["\']', block, re.I):
            return True
    ctx = re.search(
        r'data-testid=["\']socialContext["\'][^>]*aria-label=["\']([^"\']+)["\']',
        block,
        re.I,
    )
    return bool(ctx and re.search(r'pin', ctx.group(1), re.I))


def pinned_status_urls_from_html(html: str, handle: str | None = None) -> set[str]:
    """Status URLs marked Pinned on a profile timeline."""
    pinned: set[str] = set()
    for match in _ARTICLE_BLOCK_RE.finditer(html or ''):
        block = match.group(1)
        if not _article_html_is_pinned(block):
            continue
        for href in re.findall(r'href=["\']([^"\']+)["\']', block, re.I):
            url = _clean_status_url(href, handle)
            if url:
                pinned.add(url)
    if pinned:
        return pinned
    for match in re.finditer(
        r'data-testid=["\']socialContext["\'][\s\S]{0,1500}?href=["\']([^"\']+/status/\d+[^"\']*)["\']',
        html or '',
        re.I,
    ):
        chunk = match.group(0)
        if not re.search(r'Pinned', chunk, re.I):
            continue
        url = _clean_status_url(match.group(1), handle)
        if url:
            pinned.add(url)
    return pinned


def collect_status_urls_from_html(html: str, handle: str, max_posts: int = 10) -> list[str]:
    seen = []
    found = set()
    skip = pinned_status_urls_from_html(html, handle)
    skip_ids = pinned_tweet_ids_from_html(html)
    candidates = []
    for match in re.finditer(r'href=["\']([^"\']+)["\']', html, re.I):
        candidates.append(match.group(1))
    for match in re.finditer(
        r'https?://(?:www\.)?(?:x|twitter)\.com/[A-Za-z0-9_]+/status/\d+',
        html,
        re.I,
    ):
        candidates.append(match.group(0))
    for href in candidates:
        url = _clean_status_url(href, handle)
        tid = status_id_from_url(url)
        if url and url not in found and url not in skip and tid not in skip_ids:
            found.add(url)
            seen.append(url)
            if len(seen) >= max_posts:
                return seen
    return seen[:max_posts]


def _first_compact_int(text) -> int | None:
    if not text:
        return None
    match = re.search(r'(\d[\d,]*(?:\.\d+)?)\s*([KMB])?', str(text), re.I)
    if not match:
        return None
    return _parse_compact_int(match.group(1), match.group(2))


def _counts_from_labels(text: str) -> dict:
    out = {
        'reply_count': None,
        'repost_count': None,
        'like_count': None,
        'view_count': None,
    }
    for match in _COUNT_LABEL.finditer(text or ''):
        n = _parse_compact_int(match.group(1), match.group(2))
        kind = match.group(3).lower()
        if kind.startswith('repl'):
            out['reply_count'] = n
        elif kind.startswith('repost'):
            out['repost_count'] = n
        elif kind.startswith('like'):
            out['like_count'] = n
        elif kind.startswith('view'):
            out['view_count'] = n
    return out


def _json_count(html: str, *keys) -> int | None:
    for key in keys:
        match = re.search(rf'"{re.escape(key)}"\s*:\s*(\d+)', html)
        if match:
            return int(match.group(1))
    return None


def _iso_date_from_html(html: str):
    match = re.search(r'<time[^>]+datetime=["\']([^"\']+)["\']', html, re.I)
    if match:
        raw = match.group(1)
        date_match = re.match(r'(\d{4}-\d{2}-\d{2})', raw)
        return date_match.group(1) if date_match else raw
    return None


def _caption_from_html(html: str):
    block = re.search(
        r'data-testid=["\']tweetText["\'][^>]*>(.*?)</div>',
        html,
        re.I | re.DOTALL,
    )
    if block:
        text = re.sub(r'<img[^>]+alt=["\']([^"\']*)["\'][^>]*>', r'\1', block.group(1), flags=re.I)
        text = re.sub(r'<[^>]+>', '', text)
        text = unescape(re.sub(r'\s+', ' ', text)).strip()
        if text:
            return text
    desc = re.search(
        r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']',
        html,
        re.I,
    )
    if desc:
        return unescape(desc.group(1)).strip()
    return None


def _image_from_html(html: str):
    match = re.search(
        r'data-testid=["\']tweetPhoto["\'][^>]*>.*?src=["\'](https://pbs\.twimg\.com/[^"\']+)["\']',
        html,
        re.I | re.DOTALL,
    )
    if match:
        return unescape(match.group(1))
    match = re.search(r'(https://pbs\.twimg\.com/media/[^"\'\s]+)', html)
    if match:
        return match.group(1)
    return None


_EXTRACT_TWEETS_JS = r"""
function articleIsPinned(art) {
  var labeled = art.querySelectorAll('[aria-label], [title]');
  for (var k = 0; k < labeled.length; k++) {
    var al = (labeled[k].getAttribute('aria-label') || labeled[k].getAttribute('title') || '');
    if (/pin(ned)?(\b|$)/i.test(al) && !/spin|pink|pinpoint/i.test(al)) return true;
  }
  var ctxs = art.querySelectorAll('[data-testid="socialContext"]');
  for (var c = 0; c < ctxs.length; c++) {
    var ctx = ctxs[c];
    var t = ((ctx.innerText || ctx.textContent || '') + ' ' + (ctx.getAttribute('aria-label') || '')).toLowerCase();
    if (/pin|épingle|angeheftet|fijad|fixado/.test(t)) return true;
    if (!(ctx.innerText || '').trim() && ctx.querySelector('svg')) return true;
  }
  var head = (art.innerText || '').slice(0, 160);
  if (/^\s*Pinned\b/i.test(head)) return true;
  var userName = art.querySelector('[data-testid="User-Name"]');
  if (userName) {
    var svgs = userName.querySelectorAll('svg[aria-label], svg[title]');
    for (var s = 0; s < svgs.length; s++) {
      var sl = (svgs[s].getAttribute('aria-label') || svgs[s].getAttribute('title') || '');
      if (/pin/i.test(sl)) return true;
    }
  }
  return false;
}
var handle = __HANDLE__;
var maxPosts = __MAX__;
var want = (handle || '').toLowerCase();
var out = [];
var seen = {};
var articles = document.querySelectorAll('article[data-testid="tweet"]');
for (var i = 0; i < articles.length; i++) {
  var art = articles[i];
  var links = art.querySelectorAll('a[href*="/status/"]');
  var user = '', tid = '';
  for (var j = 0; j < links.length; j++) {
    var href = links[j].getAttribute('href') || '';
    if (/\/(analytics|photo|quotes|retweets)\b/i.test(href)) continue;
    var m = href.match(/\/([A-Za-z0-9_]+)\/status\/(\d+)/);
    if (m) { user = m[1]; tid = m[2]; break; }
  }
  if (!tid) continue;
  if (want && user.toLowerCase() !== want) continue;
  if (articleIsPinned(art)) continue;
  var url = 'https://x.com/' + user + '/status/' + tid;
  if (seen[url]) continue;
  seen[url] = true;
  var textEl = art.querySelector('[data-testid="tweetText"]');
  var timeEl = art.querySelector('time');
  var img = art.querySelector('[data-testid="tweetPhoto"] img, [data-testid="tweetPhoto"] image');
  var video = art.querySelector('[data-testid="videoPlayer"], video');
  var group = art.querySelector('div[role="group"]');
  var reply = art.querySelector('[data-testid="reply"]');
  var rt = art.querySelector('[data-testid="retweet"]');
  var like = art.querySelector('[data-testid="like"]');
  out.push({
    post_url: url,
    caption: textEl ? (textEl.innerText || '').trim() : null,
    date: timeEl ? (timeEl.getAttribute('datetime') || '') : null,
    image_src: img ? (img.getAttribute('src') || img.href || null) : null,
    has_video: !!video,
    aria: group ? (group.getAttribute('aria-label') || '') : '',
    reply_text: reply ? (reply.innerText || reply.getAttribute('aria-label') || '') : '',
    repost_text: rt ? (rt.innerText || rt.getAttribute('aria-label') || '') : '',
    like_text: like ? (like.innerText || like.getAttribute('aria-label') || '') : '',
  });
  if (out.length >= maxPosts) break;
}
return out;
"""


def _item_from_dom(raw: dict) -> dict:
    date_raw = raw.get('date') or ''
    date_m = re.match(r'(\d{4}-\d{2}-\d{2})', date_raw)
    blob = ' '.join(
        str(raw.get(k) or '')
        for k in ('aria', 'reply_text', 'repost_text', 'like_text')
    )
    counts = _counts_from_labels(blob)
    if counts['reply_count'] is None:
        counts['reply_count'] = _first_compact_int(raw.get('reply_text'))
    if counts['repost_count'] is None:
        counts['repost_count'] = _first_compact_int(raw.get('repost_text'))
    if counts['like_count'] is None:
        counts['like_count'] = _first_compact_int(raw.get('like_text'))
    image_src = raw.get('image_src') or None
    media_type = 'text'
    if raw.get('has_video'):
        media_type = 'video'
    elif image_src:
        media_type = 'image'
    caption = (raw.get('caption') or '').strip() or None
    return {
        'post_url': raw.get('post_url'),
        'date': date_m.group(1) if date_m else (date_raw or None),
        'caption': caption,
        'image_src': image_src,
        'media_type': media_type,
        'like_count': counts['like_count'],
        'reply_count': counts['reply_count'],
        'repost_count': counts['repost_count'],
        'view_count': counts['view_count'],
    }


def _extract_tweets_js(handle: str, max_posts: int) -> str:
    body = (
        _EXTRACT_TWEETS_JS
        .replace('__HANDLE__', json.dumps(handle or ''))
        .replace('__MAX__', str(int(max_posts or 20)))
    )
    return f'(function(){{ {body} }})()'


def extract_tweets_via_dom(sb, handle: str, max_posts: int, skip_ids: set[str] | None = None) -> list[dict]:
    try:
        raw = sb.execute_script(_extract_tweets_js(handle, max_posts + len(skip_ids or ())))
    except Exception as e:
        print(f'  DOM extract failed: {e}')
        return []
    skip_ids = skip_ids or set()
    items = []
    for row in raw or []:
        if not isinstance(row, dict) or not row.get('post_url'):
            continue
        tid = status_id_from_url(row.get('post_url'))
        if tid and tid in skip_ids:
            continue
        items.append(_item_from_dom(row))
    return items


def parse_tweet_from_html(html: str, status_url: str) -> dict:
    try:
        caption = _caption_from_html(html)
        date_text = _iso_date_from_html(html)
        image_src = _image_from_html(html)
        counts = _counts_from_labels(html)
        if counts['like_count'] is None:
            counts['like_count'] = _json_count(html, 'favorite_count', 'like_count', 'favourites_count')
        if counts['reply_count'] is None:
            counts['reply_count'] = _json_count(html, 'reply_count')
        if counts['repost_count'] is None:
            counts['repost_count'] = _json_count(html, 'retweet_count', 'repost_count')
        if counts['view_count'] is None:
            counts['view_count'] = _json_count(html, 'view_count', 'views')

        media_type = 'image' if image_src else 'text'
        if re.search(r'data-testid=["\']videoPlayer["\']', html, re.I) or '/tweet_video/' in (html or ''):
            media_type = 'video'

        return {
            'post_url': status_url,
            'date': date_text,
            'caption': caption,
            'image_src': image_src,
            'media_type': media_type,
            'like_count': counts['like_count'],
            'reply_count': counts['reply_count'],
            'repost_count': counts['repost_count'],
            'view_count': counts['view_count'],
        }
    except Exception as e:
        print(f'    parse fallback: {e}')
        return {
            'post_url': status_url,
            'date': None,
            'caption': None,
            'image_src': None,
            'media_type': 'text',
            'like_count': None,
            'reply_count': None,
            'repost_count': None,
            'view_count': None,
        }


def phase1_collect_timeline(sb, profile_url: str, max_posts: int) -> list[dict]:
    handle = _handle_from_url(profile_url)
    sb.open(profile_url)
    time.sleep(6)
    page_html = ''
    try:
        page_html = sb.get_page_source() or ''
    except Exception:
        page_html = ''
    skip_ids = pinned_tweet_ids_from_html(page_html)
    for url in pinned_status_urls_from_html(page_html, handle):
        tid = status_id_from_url(url)
        if tid:
            skip_ids.add(tid)
    if skip_ids:
        print(f'  Skipping pinned tweet id(s): {", ".join(sorted(skip_ids))}')
    by_url = {}
    last_len = -1
    stagnant = 0
    for _ in range(max(24, int(max_posts) + 8)):
        for item in extract_tweets_via_dom(sb, handle, max_posts, skip_ids=skip_ids):
            url = item.get('post_url')
            tid = status_id_from_url(url)
            if tid and tid in skip_ids:
                continue
            if url and url not in by_url:
                by_url[url] = item
        if len(by_url) >= max_posts:
            break
        if len(by_url) == last_len:
            stagnant += 1
            if stagnant >= 3:
                break
        else:
            stagnant = 0
        last_len = len(by_url)
        try:
            sb.execute_script('window.scrollTo(0, document.body.scrollHeight);')
        except Exception:
            pass
        time.sleep(2)
    return list(by_url.values())[:max_posts]


def phase2_scrape_post(sb, status_url: str) -> dict:
    sb.open(status_url)
    time.sleep(4)
    handle = _handle_from_url(status_url)
    dom = extract_tweets_via_dom(sb, handle, 1)
    if dom and (dom[0].get('caption') or dom[0].get('like_count') is not None):
        return dom[0]
    html = sb.get_page_source()
    return parse_tweet_from_html(html, status_url)


def main(PROFILE_URL: str = 'https://x.com/example', MAX_POSTS: int = 10):
    print('\n' + '═' * 65)
    print('X Posts Scraper (counts only)')
    print(f'Profile: {PROFILE_URL}  max={MAX_POSTS}')
    print('═' * 65)

    _require_cookies()
    items = []
    with SB(uc=True, headless=False, xvfb=True, window_size='1280,900') as sb:
        login(sb)
        html = sb.get_page_source()
        cur = ''
        try:
            cur = sb.driver.current_url
        except Exception:
            pass
        if _looks_like_login_page(html, cur):
            raise RuntimeError(
                'X login page detected — cookies missing or session expired.'
            )
        items = phase1_collect_timeline(sb, PROFILE_URL, MAX_POSTS)
        print(f'  Timeline DOM collected {len(items)} tweets')
        filled = sum(1 for i in items if i.get('caption') or i.get('like_count') is not None)
        if not items:
            handle = _handle_from_url(PROFILE_URL)
            page_html = sb.get_page_source()
            skip_ids = pinned_tweet_ids_from_html(page_html)
            urls = [
                u for u in collect_status_urls_from_html(page_html, handle, MAX_POSTS + len(skip_ids))
                if status_id_from_url(u) not in skip_ids
            ][:MAX_POSTS]
            print(f'  Fallback: {len(urls)} status URLs from HTML')
            for i, url in enumerate(urls, 1):
                print(f'  [{i}/{len(urls)}] {url}')
                items.append(phase2_scrape_post(sb, url))
        elif filled < len(items):
            print(f'  Filling {len(items) - filled} sparse tweets via status pages')
            for i, item in enumerate(items, 1):
                if item.get('caption') or item.get('like_count') is not None:
                    continue
                print(f'  [{i}/{len(items)}] {item.get("post_url")}')
                items[i - 1] = phase2_scrape_post(sb, item['post_url'])

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    print(f'\n Saved {len(items)} posts to {OUTPUT_FILE}')
    return items


if __name__ == '__main__':
    main()
