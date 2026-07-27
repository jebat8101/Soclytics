"""Threads posts scraper via SeleniumBase.

Collects profile post URLs, then per post scrapes:
  - caption / date / media from Meta ``data-sjs`` ``thread_items``
  - replies (author + text) from the same hydration payload + DOM
  - likes / reposts via activity dialogs (DOM) when available
"""
import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from html import unescape
from urllib.parse import urljoin

from seleniumbase import SB

from platforms.threads.about_sb import (
    _looks_like_login_page,
    _nested_lookup,
    _require_cookies,
    login,
)

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

OUTPUT_FILE = 'threads_posts.json'


def _clean_post_url(href: str):
    if not href:
        return None
    href = href.split('?')[0].split('#')[0]
    match = re.search(
        r'(https?://(?:www\.)?threads\.(?:com|net)/@[A-Za-z0-9._]+/post/[A-Za-z0-9_-]+)/?',
        href,
    )
    if match:
        return match.group(1)
    match = re.search(r'(/@[A-Za-z0-9._]+/post/[A-Za-z0-9_-]+)/?', href)
    if match:
        return 'https://www.threads.com' + match.group(1)
    return None


def collect_post_urls_from_html(html: str, max_posts: int = 10) -> list[str]:
    seen = []
    found = set()
    for match in re.finditer(
        r'href=["\']([^"\']*?/@[A-Za-z0-9._]+/post/[A-Za-z0-9_-]+/?)[^"\']*["\']',
        html,
        re.I,
    ):
        url = _clean_post_url(urljoin('https://www.threads.com/', match.group(1)))
        if url and url not in found:
            found.add(url)
            seen.append(url)
            if len(seen) >= max_posts:
                return seen

    for match in re.finditer(r'"code"\s*:\s*"([A-Za-z0-9_-]+)"', html):
        # Prefer full /@user/post/CODE when username nearby; else skip orphan codes.
        pass

    for match in re.finditer(
        r'"username"\s*:\s*"([^"]+)".{0,400}?"code"\s*:\s*"([A-Za-z0-9_-]+)"',
        html,
        re.DOTALL,
    ):
        url = f'https://www.threads.com/@{match.group(1)}/post/{match.group(2)}'
        if url not in found:
            found.add(url)
            seen.append(url)
            if len(seen) >= max_posts:
                return seen

    return seen[:max_posts]


def _meta_content(html: str, prop=None, name=None):
    if prop:
        pat = rf'<meta[^>]+property=["\']{re.escape(prop)}["\'][^>]+content=["\']([^"\']+)["\']'
        match = re.search(pat, html, re.I)
        if not match:
            pat = rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']{re.escape(prop)}["\']'
            match = re.search(pat, html, re.I)
    else:
        pat = rf'<meta[^>]+name=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']+)["\']'
        match = re.search(pat, html, re.I)
        if not match:
            pat = rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']{re.escape(name)}["\']'
            match = re.search(pat, html, re.I)
    return unescape(match.group(1)).strip() if match else None


def _extract_sjs_blobs(html: str) -> list[str]:
    blobs = []
    for match in re.finditer(
        r'<script[^>]*type=["\']application/json["\'][^>]*>(.*?)</script>',
        html,
        re.DOTALL | re.I,
    ):
        text = match.group(1).strip()
        if text:
            blobs.append(text)
    return blobs


def _ts_to_date(ts):
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime('%Y-%m-%d')
    except (ValueError, OSError, TypeError):
        return None


def _image_from_post(post: dict):
    if not isinstance(post, dict):
        return None
    carousel = post.get('carousel_media') or []
    if isinstance(carousel, list):
        for media in carousel:
            if not isinstance(media, dict):
                continue
            versions = (media.get('image_versions2') or {}).get('candidates') or []
            if versions and isinstance(versions[0], dict):
                return versions[0].get('url')
    image_versions = (post.get('image_versions2') or {}).get('candidates') or []
    if image_versions and isinstance(image_versions[0], dict):
        return image_versions[0].get('url')
    return None


def _video_from_post(post: dict):
    versions = post.get('video_versions') or []
    if isinstance(versions, list) and versions:
        first = versions[0]
        if isinstance(first, dict):
            return first.get('url')
    return None


def _parse_thread_item(item: dict) -> dict | None:
    if not isinstance(item, dict):
        return None
    post = item.get('post') if isinstance(item.get('post'), dict) else item
    if not isinstance(post, dict):
        return None
    user = post.get('user') if isinstance(post.get('user'), dict) else {}
    username = user.get('username') or ''
    code = post.get('code') or ''
    caption_obj = post.get('caption')
    text = None
    if isinstance(caption_obj, dict):
        text = caption_obj.get('text')
    elif isinstance(caption_obj, str):
        text = caption_obj
    text = text or post.get('text')

    image_src = _image_from_post(post)
    video_src = _video_from_post(post)
    if video_src and not image_src:
        media_type = 'video'
        image_src = video_src
    elif image_src:
        media_type = 'image'
    else:
        media_type = 'text'

    post_url = None
    if username and code:
        post_url = f'https://www.threads.com/@{username}/post/{code}'

    text_post_info = post.get('text_post_app_info') or {}
    repost_count = None
    reply_count = None
    if isinstance(text_post_info, dict):
        reply_count = text_post_info.get('direct_reply_count')
        repost_count = text_post_info.get('repost_count')

    return {
        'post_url': post_url,
        'date': _ts_to_date(post.get('taken_at')),
        'caption': text,
        'image_src': image_src,
        'media_type': media_type,
        'username': username,
        'like_count': post.get('like_count'),
        'reply_count': reply_count,
        'repost_count': repost_count,
        'name': user.get('full_name') or username,
        'profile_url': f'https://www.threads.com/@{username}/' if username else None,
    }


def _thread_items_from_html(html: str) -> list[dict]:
    items = []
    for blob in _extract_sjs_blobs(html):
        if 'thread_items' not in blob:
            continue
        try:
            data = json.loads(blob)
        except json.JSONDecodeError:
            continue
        for group in _nested_lookup('thread_items', data):
            if not isinstance(group, list):
                continue
            for item in group:
                parsed = _parse_thread_item(item)
                if parsed:
                    items.append(parsed)
    return items


def _iso_date_from_html(html: str):
    match = re.search(r'<time[^>]+datetime=["\']([^"\']+)["\']', html, re.I)
    if match:
        raw = match.group(1)
        date_match = re.match(r'(\d{4}-\d{2}-\d{2})', raw)
        if date_match:
            return date_match.group(1)
        return raw
    match = re.search(r'"taken_at"\s*:\s*(\d+)', html)
    if match:
        return _ts_to_date(match.group(1))
    return None


def _caption_from_html(html: str):
    desc = _meta_content(html, prop='og:description') or ''
    match = re.search(r'"text"\s*:\s*"((?:\\.|[^"\\])*)"', html)
    if match:
        try:
            return json.loads(f'"{match.group(1)}"')
        except json.JSONDecodeError:
            return unescape(match.group(1))
    return desc or None


def _image_from_html(html: str):
    img = _meta_content(html, prop='og:image')
    if img:
        return img
    match = re.search(r'"image"\s*:\s*"([^"]+)"', html)
    if match:
        return match.group(1).replace('\\/', '/')
    return None


SCRAPE_PROFILE_LINKS_JS = """
var seen = {};
var result = [];
var root = document.querySelector('[role="dialog"]') || document.body;
var anchors = root.querySelectorAll('a[href*="/@"]');
for (var i = 0; i < anchors.length; i++) {
    var a = anchors[i];
    var href = a.href || '';
    var m = href.match(/https?:\\/\\/(?:www\\.)?threads\\.(?:com|net)\\/@([A-Za-z0-9._]+)\\/?/);
    if (!m) continue;
    if (href.indexOf('/post/') !== -1) continue;
    var user = m[1];
    var url = 'https://www.threads.com/@' + user + '/';
    if (seen[url]) continue;
    var name = (a.innerText || '').trim().split('\\n')[0].trim();
    if (!name || name.length < 1) name = user;
    seen[url] = true;
    result.push({ name: name, profile_url: url });
}
return result;
"""


CLICK_ACTIVITY_JS = """
var labels = ['view activity', 'activity', 'likes', 'like', 'reposts', 'repost'];
var nodes = document.querySelectorAll('a, button, div[role="button"], span[role="button"]');
for (var i = 0; i < nodes.length; i++) {
    var el = nodes[i];
    var t = ((el.getAttribute('aria-label') || '') + ' ' + (el.innerText || '')).toLowerCase().trim();
    if (!t) continue;
    for (var j = 0; j < labels.length; j++) {
        if (t === labels[j] || t.indexOf(labels[j]) !== -1) {
            try { el.click(); return labels[j]; } catch (e) {}
        }
    }
}
return null;
"""


CLICK_TAB_JS = """
var want = arguments[0];
var nodes = document.querySelectorAll('a, button, div[role="tab"], div[role="button"], span');
for (var i = 0; i < nodes.length; i++) {
    var el = nodes[i];
    var t = ((el.getAttribute('aria-label') || '') + ' ' + (el.innerText || '')).toLowerCase().trim();
    if (!t) continue;
    if (t === want || t.indexOf(want) !== -1) {
        try { el.click(); return true; } catch (e) {}
    }
}
return false;
"""


CLOSE_DIALOG_JS = """
var btn = document.querySelector('[aria-label="Close"], [aria-label="Dismiss"]');
if (btn) { try { btn.click(); return true; } catch (e) {} }
var dialog = document.querySelector('[role="dialog"]');
if (dialog) {
    var close = dialog.querySelector('div[role="button"], button');
    if (close) { try { close.click(); return true; } catch (e) {} }
}
document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));
return false;
"""


EXPAND_REPLIES_JS = """
var clicked = 0;
var nodes = document.querySelectorAll('button, div[role="button"], a');
for (var i = 0; i < nodes.length; i++) {
    var t = ((nodes[i].innerText || '') + ' ' + (nodes[i].getAttribute('aria-label') || '')).toLowerCase();
    if (t.indexOf('view') !== -1 && (t.indexOf('repl') !== -1 || t.indexOf('more') !== -1)) {
        try { nodes[i].click(); clicked++; } catch (e) {}
    }
}
return clicked;
"""


COLLECT_POSTS_JS = """
var seen = new Set();
var result = [];
document.querySelectorAll('a[href*="/post/"]').forEach(function(a) {
    var href = a.href || '';
    var m = href.match(/https?:\\/\\/(?:www\\.)?threads\\.(?:com|net)\\/@[A-Za-z0-9._]+\\/post\\/[A-Za-z0-9_-]+/);
    if (!m) return;
    if (seen.has(m[0])) return;
    seen.add(m[0]);
    result.push(m[0]);
});
return result;
"""


def _merge_interactors(base: list, extra: list, with_text: bool) -> list:
    seen = set()
    out = []
    for item in (base or []) + (extra or []):
        if not item:
            continue
        url = (item.get('profile_url') or '').rstrip('/') + '/'
        name = item.get('name') or ''
        text = item.get('comment_text', '') if with_text else ''
        key = (url.lower(), text)
        if not url or key in seen:
            continue
        seen.add(key)
        row = {'name': name or url.split('/@')[-1].strip('/'), 'profile_url': url}
        if with_text:
            row['comment_text'] = text or ''
        out.append(row)
    return out


def parse_post_from_html(html: str, post_url: str) -> dict:
    """Parse a single post page into threads_posts.json item shape."""
    thread_items = _thread_items_from_html(html)

    main = None
    replies = []
    post_code = None
    m = re.search(r'/post/([A-Za-z0-9_-]+)', post_url)
    if m:
        post_code = m.group(1)

    for item in thread_items:
        item_url = item.get('post_url') or ''
        if post_code and post_code in item_url and main is None:
            main = item
            continue
        if main is None and item_url == post_url:
            main = item
            continue
        # Remaining thread_items after the main post are replies.
        if item.get('username'):
            uname = item.get('username')
            replies.append({
                'name': item.get('name') or uname,
                'profile_url': item.get('profile_url')
                or f'https://www.threads.com/@{uname}/',
                'comment_text': item.get('caption') or '',
            })

    if main is None and thread_items:
        main = thread_items[0]
        replies = []
        for item in thread_items[1:]:
            if item.get('username'):
                uname = item.get('username')
                replies.append({
                    'name': item.get('name') or uname,
                    'profile_url': item.get('profile_url')
                    or f'https://www.threads.com/@{uname}/',
                    'comment_text': item.get('caption') or '',
                })

    image_src = (main or {}).get('image_src') or _image_from_html(html)
    caption = (main or {}).get('caption') or _caption_from_html(html)
    date = (main or {}).get('date') or _iso_date_from_html(html)
    media_type = (main or {}).get('media_type') or ('image' if image_src else 'text')

    return {
        'post_url': post_url,
        'date': date,
        'caption': caption,
        'image_src': image_src,
        'media_type': media_type,
        'like_count': (main or {}).get('like_count'),
        'reply_count': (main or {}).get('reply_count'),
        'repost_count': (main or {}).get('repost_count'),
        'replies': _merge_interactors([], replies, with_text=True),
        'likes': [],
        'reposts': [],
    }


def phase1_collect_urls(sb, profile_url: str, max_posts: int) -> list[str]:
    print(f'\nPHASE 1 - Collecting up to {max_posts} thread URLs')
    sb.open(profile_url.rstrip('/') + '/')
    time.sleep(5)
    html = sb.get_page_source()
    if _looks_like_login_page(html):
        raise RuntimeError(
            'Threads login page detected after cookie load — '
            'session expired or cookies invalid.'
        )

    urls = []
    found = set()
    no_change = 0
    for _step in range(20):
        js_urls = sb.execute_script(f'(function(){{ {COLLECT_POSTS_JS} }})()') or []
        added = 0
        for url in js_urls:
            clean = _clean_post_url(url)
            if clean and clean not in found:
                found.add(clean)
                urls.append(clean)
                added += 1
        if len(urls) >= max_posts:
            break
        if added == 0:
            no_change += 1
            if no_change >= 4:
                break
        else:
            no_change = 0
        sb.execute_script('(function(){ window.scrollBy(0, 1400); })()')
        time.sleep(2)

    if len(urls) < max_posts:
        html = sb.get_page_source()
        for url in collect_post_urls_from_html(html, max_posts):
            if url not in found:
                found.add(url)
                urls.append(url)

    # Prefer posts that belong to this profile handle.
    handle = None
    hm = re.search(r'threads\.(?:com|net)/@([A-Za-z0-9._]+)', profile_url)
    if hm:
        handle = hm.group(1).lower()
    if handle:
        own = [u for u in urls if f'/@{handle}/post/' in u.lower()]
        if own:
            urls = own

    urls = urls[:max_posts]
    print(f'   Found {len(urls)} posts')
    return urls


def _harvest_dialog_users(sb, tab_label: str | None = None) -> list[dict]:
    if tab_label:
        try:
            sb.execute_script(CLICK_TAB_JS, tab_label)
            time.sleep(2)
        except Exception:
            pass
    try:
        sb.execute_script('(function(){ var d=document.querySelector("[role=dialog]"); if(d) d.scrollTop=d.scrollHeight; })()')
        time.sleep(1)
    except Exception:
        pass
    users = sb.execute_script(f'(function(){{ {SCRAPE_PROFILE_LINKS_JS} }})()') or []
    return users if isinstance(users, list) else []


def _scrape_engagements(sb) -> tuple[list, list]:
    """Open activity UI and collect likers + reposters."""
    likes = []
    reposts = []
    try:
        clicked = sb.execute_script(f'(function(){{ {CLICK_ACTIVITY_JS} }})()')
        time.sleep(3)
        if clicked:
            likes = _merge_interactors([], _harvest_dialog_users(sb, 'like'), with_text=False)
            # Switch to reposts tab when present.
            reposts = _merge_interactors(
                [], _harvest_dialog_users(sb, 'repost'), with_text=False
            )
            # If tab switch failed, first harvest may mix both — keep as likes.
            if not likes and not reposts:
                both = _harvest_dialog_users(sb)
                likes = _merge_interactors([], both, with_text=False)
            sb.execute_script(f'(function(){{ {CLOSE_DIALOG_JS} }})()')
            time.sleep(1)
    except Exception as e:
        print(f'    [engagement] dialog scrape failed: {e}')
    return likes, reposts


def phase2_scrape_post(sb, post_url: str, idx: int, total: int) -> dict:
    print(f'\n  [{idx}/{total}] {post_url}')
    sb.open(post_url)
    time.sleep(5)

    try:
        sb.execute_script(f'(function(){{ {EXPAND_REPLIES_JS} }})()')
        time.sleep(2)
        for _ in range(6):
            sb.execute_script('(function(){ window.scrollBy(0, 900); })()')
            time.sleep(1.2)
            sb.execute_script(f'(function(){{ {EXPAND_REPLIES_JS} }})()')
    except Exception:
        pass

    html = sb.get_page_source()
    result = parse_post_from_html(html, post_url)

    # Supplement replies from live DOM profile links under the thread.
    author = None
    am = re.search(r'threads\.(?:com|net)/@([A-Za-z0-9._]+)/post/', post_url)
    if am:
        author = am.group(1).lower()
    try:
        dom_users = sb.execute_script(f'(function(){{ {SCRAPE_PROFILE_LINKS_JS} }})()') or []
        reply_extra = []
        for u in dom_users:
            url = (u.get('profile_url') or '').lower()
            if author and f'/@{author}/' in url:
                continue
            reply_extra.append({
                'name': u.get('name'),
                'profile_url': u.get('profile_url'),
                'comment_text': '',
            })
        result['replies'] = _merge_interactors(result.get('replies'), reply_extra, with_text=True)
    except Exception:
        pass

    likes, reposts = _scrape_engagements(sb)
    result['likes'] = _merge_interactors(result.get('likes'), likes, with_text=False)
    result['reposts'] = _merge_interactors(result.get('reposts'), reposts, with_text=False)

    # Strip author from likes/reposts.
    if author:
        result['likes'] = [
            x for x in result['likes']
            if f'/@{author}/' not in (x.get('profile_url') or '').lower()
        ]
        result['reposts'] = [
            x for x in result['reposts']
            if f'/@{author}/' not in (x.get('profile_url') or '').lower()
        ]

    print(f"    date    : {result.get('date')}")
    print(f"    caption : {(result.get('caption') or '')[:60]}")
    print(f"    replies : {len(result.get('replies') or [])}")
    print(f"    likes   : {len(result.get('likes') or [])}")
    print(f"    reposts : {len(result.get('reposts') or [])}")
    return result


def main(PROFILE_URL: str, MAX_POSTS: int = 10):
    print('\n' + '═' * 65)
    print('Threads Posts Scraper')
    print(f'Profile: {PROFILE_URL}  max={MAX_POSTS}')
    print('═' * 65)

    _require_cookies()
    results = []
    with SB(uc=True, headless=False, xvfb=True, window_size='1280,900') as sb:
        login(sb)
        post_links = phase1_collect_urls(sb, PROFILE_URL, MAX_POSTS)

        print(f"\n{'═' * 65}")
        print(f'PHASE 2 - Scraping {len(post_links)} posts + engagements')
        print('═' * 65)

        for i, post_url in enumerate(post_links, 1):
            try:
                results.append(phase2_scrape_post(sb, post_url, i, len(post_links)))
            except Exception as e:
                print(f'    Error on post {i}: {e}')
                results.append(
                    {
                        'post_url': post_url,
                        'date': None,
                        'caption': None,
                        'image_src': None,
                        'media_type': 'text',
                        'replies': [],
                        'likes': [],
                        'reposts': [],
                        'error': str(e),
                    }
                )
            time.sleep(2)

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f'\n Saved to {OUTPUT_FILE} ({len(results)} posts)')
    return results


if __name__ == '__main__':
    import sys

    url = sys.argv[1] if len(sys.argv) > 1 else input('Profile URL: ').strip()
    main(url)
