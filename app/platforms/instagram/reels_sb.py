"""
Instagram reels scraper via SeleniumBase.

Best-effort: collect ``/reel/`` anchor hrefs (profile reels tab + grid),
then open each reel for caption/date/comments via meta/DOM/JSON.
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

from core.date_filters import filter_dated_items
from core.depth import cap_label, has_room, normalize_cap, take_cap
from platforms.instagram.about_sb import login, _require_cookies, _looks_like_login_page
from platforms.instagram.posts_sb import (
    _iso_date_from_html,
    _caption_from_html,
    _comments_from_html,
    _engagement_counts_from_html,
)

OUTPUT_FILE = "ig_reels.json"


def _clean_reel_url(href: str):
    if not href:
        return None
    href = href.split('?')[0].split('#')[0]
    m = re.search(
        r'(https?://(?:www\.)?instagram\.com/reels?/[A-Za-z0-9_-]+)/?', href
    )
    if m:
        code_m = re.search(r'/reels?/([A-Za-z0-9_-]+)', m.group(1))
        if code_m:
            return f'https://www.instagram.com/reel/{code_m.group(1)}/'
    m = re.search(r'/reels?/([A-Za-z0-9_-]+)', href)
    if m:
        return f'https://www.instagram.com/reel/{m.group(1)}/'
    return None


def collect_reel_urls_from_html(html: str, max_reels: int = 10) -> list:
    cap = normalize_cap(max_reels)
    seen = []
    found = set()
    for m in re.finditer(
        r'href=["\']([^"\']*?/reels?/[A-Za-z0-9_-]+/?)[^"\']*["\']', html, re.I
    ):
        url = _clean_reel_url(urljoin('https://www.instagram.com/', m.group(1)))
        if url and url not in found:
            found.add(url)
            seen.append(url)
            if not has_room(len(seen), cap):
                return seen
    return take_cap(seen, cap)


def parse_reel_from_html(html: str, reel_url: str) -> dict:
    """Parse a reel page into the Task 7 ``ig_reels.json`` item shape."""
    if _looks_like_login_page(html):
        raise RuntimeError(
            "Instagram login page detected — cookies missing or session expired."
        )
    result = {
        'reel_url': reel_url,
        'date': _iso_date_from_html(html),
        'caption': _caption_from_html(html),
        'comments': _comments_from_html(html),
    }
    result.update(_engagement_counts_from_html(html))
    return result


COLLECT_REELS_JS = """
var seen = new Set();
var result = [];
document.querySelectorAll('a[href*="/reel/"], a[href*="/reels/"]').forEach(function(a) {
    var href = a.href || '';
    var m = href.match(/https?:\\/\\/(?:www\\.)?instagram\\.com\\/reels?\\/[A-Za-z0-9_-]+/);
    if (!m) return;
    var code = m[0].match(/\\/reels?\\/([A-Za-z0-9_-]+)/);
    if (!code) return;
    var clean = 'https://www.instagram.com/reel/' + code[1] + '/';
    if (seen.has(clean)) return;
    seen.add(clean);
    result.push(clean);
});
return result;
"""


def _reels_tab_url(profile_url: str) -> str:
    return profile_url.rstrip('/') + '/reels/'


def phase1_collect_reels(sb, profile_url: str, max_reels: int) -> list:
    cap = normalize_cap(max_reels)
    print(f"\nPHASE 1 — Collecting up to {cap_label(cap)} reel URLs")
    urls = []
    found = set()

    for page_url in (_reels_tab_url(profile_url), profile_url.rstrip('/') + '/'):
        sb.open(page_url)
        time.sleep(5)
        html = sb.get_page_source()
        if _looks_like_login_page(html):
            raise RuntimeError(
                "Instagram login page detected after cookie load — "
                "session expired or cookies invalid."
            )

        last_len = -1
        stagnant = 0
        max_rounds = 2000 if cap is None else 6
        for _step in range(max_rounds):
            js_urls = sb.execute_script(
                f"(function(){{ {COLLECT_REELS_JS} }})()"
            ) or []
            for u in js_urls:
                clean = _clean_reel_url(u)
                if clean and clean not in found:
                    found.add(clean)
                    urls.append(clean)
            if not has_room(len(urls), cap):
                break
            if len(urls) == last_len:
                stagnant += 1
                if stagnant >= 3:
                    break
            else:
                stagnant = 0
            last_len = len(urls)
            sb.execute_script("(function(){ window.scrollBy(0, 1200); })()")
            time.sleep(2)

        for u in collect_reel_urls_from_html(html, cap):
            if u not in found:
                found.add(u)
                urls.append(u)

        if not has_room(len(urls), cap):
            break

    urls = take_cap(urls, cap)
    print(f"   Found {len(urls)} reels")
    return urls


def phase2_scrape_reel(sb, reel_url: str, idx: int, total: int) -> dict:
    print(f"\n  [{idx}/{total}] {reel_url}")
    sb.open(reel_url)
    time.sleep(5)
    html = sb.get_page_source()
    try:
        sb.execute_script("""
        (function(){
          var btns = document.querySelectorAll('button, div[role="button"]');
          for (var i = 0; i < btns.length; i++) {
            var t = (btns[i].innerText || '').toLowerCase();
            if (t.includes('view all') || t.includes('more comment') || t.includes('comment')) {
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

    result = parse_reel_from_html(html, reel_url)
    print(f"    date    : {result.get('date')}")
    print(f"    caption : {(result.get('caption') or '')[:60]}")
    print(f"    comments: {len(result.get('comments') or [])}")
    return result


def main(PROFILE_URL: str, MAX_REELS: int = 10, START_DATE=None, END_DATE=None):
    """
    Live scrape Instagram reels → ``ig_reels.json``.

    NOTE: Selectors may need live tuning against authorized sessions.
    """
    cap = normalize_cap(MAX_REELS)
    print("\n" + "═" * 65)
    print("Instagram Reels Scraper")
    print(f"Profile: {PROFILE_URL}  max={cap_label(cap)}")
    print("═" * 65)

    _require_cookies()
    results = []

    with SB(uc=True, headless=False, xvfb=True, window_size="1280,900") as sb:
        login(sb)
        reel_links = phase1_collect_reels(sb, PROFILE_URL, cap)

        print(f"\n{'═'*65}")
        print(f"PHASE 2 — Scraping {len(reel_links)} reels")
        print("═" * 65)

        for i, reel_url in enumerate(reel_links, 1):
            try:
                results.append(phase2_scrape_reel(sb, reel_url, i, len(reel_links)))
            except Exception as e:
                print(f"    Error on reel {i}: {e}")
                results.append({
                    'reel_url': reel_url,
                    'date': None,
                    'caption': None,
                    'comments': [],
                    'error': str(e),
                })
            time.sleep(2)

    results = filter_dated_items(results, START_DATE, END_DATE)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n Saved to {OUTPUT_FILE} ({len(results)} reels)")
    return results


if __name__ == "__main__":
    import sys
    url = sys.argv[1] if len(sys.argv) > 1 else input("Profile URL: ").strip()
    main(url)
