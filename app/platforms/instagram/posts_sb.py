"""
Instagram posts scraper via SeleniumBase.

Best-effort: collect ``/p/`` anchor hrefs from the profile grid, then open
each post for caption/date/image/comments via meta tags and light DOM/JSON.
Selectors may need live tuning when Instagram changes markup.

Requires cookie pickle at ``platforms.instagram.constants.COOKIE_FILE``.
Raises if cookies are missing or a login page is detected.
"""
from seleniumbase import SB
import time
import os
import subprocess
import json
import re
from html import unescape
from urllib.parse import urljoin

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

from platforms.instagram.about_sb import login, _require_cookies, _looks_like_login_page
from core.counts import as_int

OUTPUT_FILE = "ig_posts.json"


def _clean_post_url(href: str):
    if not href:
        return None
    href = href.split('?')[0].split('#')[0]
    m = re.search(r'(https?://(?:www\.)?instagram\.com/p/[A-Za-z0-9_-]+)/?', href)
    if m:
        return m.group(1) + '/'
    m = re.search(r'(/p/[A-Za-z0-9_-]+)/?', href)
    if m:
        return 'https://www.instagram.com' + m.group(1) + '/'
    return None


def collect_post_urls_from_html(html: str, max_posts: int = 10) -> list:
    """Extract unique /p/ URLs from profile HTML (grid anchors + JSON)."""
    seen = []
    found = set()

    for m in re.finditer(
        r'href=["\']([^"\']*?/p/[A-Za-z0-9_-]+/?)[^"\']*["\']', html, re.I
    ):
        url = _clean_post_url(urljoin('https://www.instagram.com/', m.group(1)))
        if url and url not in found:
            found.add(url)
            seen.append(url)
            if len(seen) >= max_posts:
                return seen

    for m in re.finditer(r'"shortcode"\s*:\s*"([A-Za-z0-9_-]+)"', html):
        url = f'https://www.instagram.com/p/{m.group(1)}/'
        if url not in found:
            found.add(url)
            seen.append(url)
            if len(seen) >= max_posts:
                return seen

    return seen[:max_posts]


def _meta_content(html: str, prop=None, name=None):
    if prop:
        pat = rf'<meta[^>]+property=["\']{re.escape(prop)}["\'][^>]+content=["\']([^"\']+)["\']'
        m = re.search(pat, html, re.I)
        if not m:
            pat = rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']{re.escape(prop)}["\']'
            m = re.search(pat, html, re.I)
    else:
        pat = rf'<meta[^>]+name=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']+)["\']'
        m = re.search(pat, html, re.I)
        if not m:
            pat = rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']{re.escape(name)}["\']'
            m = re.search(pat, html, re.I)
    return unescape(m.group(1)).strip() if m else None


def _iso_date_from_html(html: str):
    m = re.search(r'<time[^>]+datetime=["\']([^"\']+)["\']', html, re.I)
    if m:
        raw = m.group(1)
        dm = re.match(r'(\d{4}-\d{2}-\d{2})', raw)
        if dm:
            return dm.group(1)
        return raw
    m = re.search(r'"taken_at_timestamp"\s*:\s*(\d+)', html)
    if m:
        try:
            from datetime import datetime, timezone
            ts = int(m.group(1))
            return datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%Y-%m-%d')
        except (ValueError, OSError):
            pass
    return None


def _caption_from_html(html: str):
    desc = _meta_content(html, prop='og:description') or ''
    m = re.search(r':\s*[“"](.+?)[”"]\s*$', desc, re.DOTALL)
    if m:
        return unescape(m.group(1)).strip()
    m = re.search(
        r'"edge_media_to_caption"[^]]*?"text"\s*:\s*"((?:\\.|[^"\\])*)"', html
    )
    if m:
        try:
            return json.loads(f'"{m.group(1)}"')
        except json.JSONDecodeError:
            return unescape(m.group(1))
    m = re.search(r'"caption"\s*:\s*"((?:\\.|[^"\\])*)"', html)
    if m:
        try:
            return json.loads(f'"{m.group(1)}"')
        except json.JSONDecodeError:
            return unescape(m.group(1))
    return desc or None


def _image_from_html(html: str):
    img = _meta_content(html, prop='og:image')
    if img:
        return img
    m = re.search(r'"display_url"\s*:\s*"(https?:[^"]+)"', html)
    if m:
        return m.group(1).replace('\\u0026', '&').replace('\\/', '/')
    return None


def _media_type_from_html(html: str) -> str:
    lower = html.lower()
    if 'og:video' in lower or '"is_video":true' in lower or '/reel/' in lower:
        return 'video'
    if 'sidecar' in lower or 'carousel' in lower:
        return 'carousel'
    return 'image'


def _comments_from_html(html: str) -> list:
    comments = []
    seen = set()
    for m in re.finditer(
        r'"username"\s*:\s*"([^"]+)".{0,200}?"text"\s*:\s*"((?:\\.|[^"\\])*)"',
        html,
        re.DOTALL,
    ):
        name = m.group(1)
        try:
            text = json.loads(f'"{m.group(2)}"')
        except json.JSONDecodeError:
            text = unescape(m.group(2))
        key = (name, text)
        if key in seen or not text:
            continue
        seen.add(key)
        comments.append({
            'name': name,
            'profile_url': f'https://www.instagram.com/{name}/',
            'comment_text': text,
        })
    return comments


def _json_int_field(html: str, key: str) -> int:
    m = re.search(rf'"{re.escape(key)}"\s*:\s*(-?\d+)', html)
    return as_int(m.group(1)) if m else 0


def _edge_count_field(html: str, edge_name: str) -> int:
    m = re.search(
        rf'"{re.escape(edge_name)}"\s*:\s*\{{[^}}]*?"count"\s*:\s*(-?\d+)',
        html,
    )
    return as_int(m.group(1)) if m else 0


def _engagement_counts_from_html(html: str) -> dict:
    like = _json_int_field(html, 'like_count') or _edge_count_field(
        html, 'edge_media_preview_like'
    )
    reply = _json_int_field(html, 'comment_count')
    repost = (
        _json_int_field(html, 'repost_count')
        or _json_int_field(html, 'reshare_count')
    )
    return {
        'like_count': like,
        'reply_count': reply,
        'repost_count': repost,
    }


def parse_post_from_html(html: str, post_url: str) -> dict:
    """Parse a single post page into the Task 7 ``ig_posts.json`` item shape."""
    if _looks_like_login_page(html):
        raise RuntimeError(
            "Instagram login page detected — cookies missing or session expired."
        )
    result = {
        'post_url': post_url,
        'date': _iso_date_from_html(html),
        'caption': _caption_from_html(html),
        'image_src': _image_from_html(html),
        'media_type': _media_type_from_html(html),
        'comments': _comments_from_html(html),
    }
    result.update(_engagement_counts_from_html(html))
    return result


COLLECT_POSTS_JS = """
var seen = new Set();
var result = [];
document.querySelectorAll('a[href*="/p/"]').forEach(function(a) {
    var href = a.href || '';
    var m = href.match(/https?:\\/\\/(?:www\\.)?instagram\\.com\\/p\\/[A-Za-z0-9_-]+/);
    if (!m) return;
    var clean = m[0] + '/';
    if (seen.has(clean)) return;
    seen.add(clean);
    result.push(clean);
});
return result;
"""


def phase1_collect_urls(sb, profile_url: str, max_posts: int) -> list:
    print(f"\nPHASE 1 — Collecting up to {max_posts} post URLs")
    sb.open(profile_url.rstrip('/') + '/')
    time.sleep(5)
    html = sb.get_page_source()
    if _looks_like_login_page(html):
        raise RuntimeError(
            "Instagram login page detected after cookie load — "
            "session expired or cookies invalid."
        )

    urls = []
    found = set()
    for _step in range(8):
        js_urls = sb.execute_script(f"(function(){{ {COLLECT_POSTS_JS} }})()") or []
        for u in js_urls:
            clean = _clean_post_url(u)
            if clean and clean not in found:
                found.add(clean)
                urls.append(clean)
        if len(urls) >= max_posts:
            break
        sb.execute_script("(function(){ window.scrollBy(0, 1200); })()")
        time.sleep(2)

    if len(urls) < max_posts:
        for u in collect_post_urls_from_html(html, max_posts):
            if u not in found:
                found.add(u)
                urls.append(u)

    urls = urls[:max_posts]
    print(f"   Found {len(urls)} posts")
    return urls


def phase2_scrape_post(sb, post_url: str, idx: int, total: int) -> dict:
    print(f"\n  [{idx}/{total}] {post_url}")
    sb.open(post_url)
    time.sleep(5)
    html = sb.get_page_source()
    try:
        sb.execute_script("""
        (function(){
          var btns = document.querySelectorAll('button, div[role="button"]');
          for (var i = 0; i < btns.length; i++) {
            var t = (btns[i].innerText || '').toLowerCase();
            if (t.includes('view all') || t.includes('more comment')) {
              btns[i].click(); return true;
            }
          }
          return false;
        })();
        """)
        time.sleep(2)
        html = sb.get_page_source()
    except Exception:
        pass

    result = parse_post_from_html(html, post_url)
    print(f"    date    : {result.get('date')}")
    print(f"    caption : {(result.get('caption') or '')[:60]}")
    print(f"    comments: {len(result.get('comments') or [])}")
    return result


def main(PROFILE_URL: str, MAX_POSTS: int = 10):
    """
    Live scrape Instagram posts → ``ig_posts.json``.

    NOTE: Selectors may need live tuning against authorized sessions.
    """
    print("\n" + "═" * 65)
    print("Instagram Posts Scraper")
    print(f"Profile: {PROFILE_URL}  max={MAX_POSTS}")
    print("═" * 65)

    _require_cookies()
    results = []

    with SB(uc=True, headless=False, xvfb=True, window_size="1280,900") as sb:
        login(sb)
        post_links = phase1_collect_urls(sb, PROFILE_URL, MAX_POSTS)

        print(f"\n{'═'*65}")
        print(f"PHASE 2 — Scraping {len(post_links)} posts")
        print("═" * 65)

        for i, post_url in enumerate(post_links, 1):
            try:
                results.append(phase2_scrape_post(sb, post_url, i, len(post_links)))
            except Exception as e:
                print(f"    Error on post {i}: {e}")
                results.append({
                    'post_url': post_url,
                    'date': None,
                    'caption': None,
                    'image_src': None,
                    'media_type': 'image',
                    'comments': [],
                    'error': str(e),
                })
            time.sleep(2)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n Saved to {OUTPUT_FILE} ({len(results)} posts)")
    return results


if __name__ == "__main__":
    import sys
    url = sys.argv[1] if len(sys.argv) > 1 else input("Profile URL: ").strip()
    main(url)
