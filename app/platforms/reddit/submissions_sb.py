"""
Reddit submissions scraper via SeleniumBase.

Collects ``/user/<name>/submitted/`` on old.reddit.com, then opens each
permalink for comment authors. Requires cookie pickle at
``platforms.reddit.constants.COOKIE_FILE``. Raises if cookies are missing.
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

from platforms.reddit.about_sb import (
    login,
    _require_cookies,
    _looks_like_login_page,
    _to_old_reddit,
    _username_from_url,
)

OUTPUT_FILE = "reddit_submissions.json"


def _strip_tags(html_frag: str) -> str:
    text = re.sub(r'<[^>]+>', ' ', html_frag or '')
    return unescape(re.sub(r'\s+', ' ', text)).strip()


def _canonical_post_url(href: str):
    if not href:
        return None
    href = href.split('?')[0].split('#')[0]
    m = re.search(
        r'(?:https?://(?:www\.|old\.)?reddit\.com)?'
        r'(/r/[^/]+/comments/[A-Za-z0-9]+/[^/\s"\']*/?)',
        href,
        re.I,
    )
    if not m:
        return None
    path = m.group(1)
    if not path.endswith('/'):
        path += '/'
    return 'https://www.reddit.com' + path


def _user_profile_url(name: str) -> str:
    return f'https://www.reddit.com/user/{name}/'


def _date_from_fragment(frag: str):
    m = re.search(r'<time[^>]+datetime=["\']([^"\']+)["\']', frag, re.I)
    if m:
        dm = re.match(r'(\d{4}-\d{2}-\d{2})', m.group(1))
        if dm:
            return dm.group(1)
    m = re.search(r'data-timestamp=["\'](\d+)["\']', frag, re.I)
    if m:
        try:
            from datetime import datetime, timezone
            ts = int(m.group(1))
            if ts > 10_000_000_000:
                ts = ts / 1000.0
            return datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%Y-%m-%d')
        except (ValueError, OSError):
            pass
    return None


def _body_from_thing(frag: str):
    m = re.search(
        r'<div[^>]*class=["\'][^"\']*usertext-body[^"\']*["\'][^>]*>'
        r'.*?<div[^>]*class=["\'][^"\']*\bmd\b[^"\']*["\'][^>]*>(.*?)</div>',
        frag,
        re.DOTALL | re.I,
    )
    if m:
        return _strip_tags(m.group(1)) or None
    return None


def parse_submissions_list_from_html(html: str, max_posts: int = 10) -> list:
    """Parse old.reddit submitted listing into Task 10 submission dicts (no comments)."""
    if _looks_like_login_page(html):
        raise RuntimeError(
            "Reddit login page detected — cookies missing or session expired."
        )

    items = []
    for m in re.finditer(
        r'<div([^>]*\bthing\b[^>]*\blink\b[^>]*)>(.*?)(?=<div[^>]*\bthing\b|\Z)',
        html,
        re.DOTALL | re.I,
    ):
        attrs, body = m.group(1), m.group(2)
        frag = attrs + body

        permalink = None
        pm = re.search(r'data-permalink=["\']([^"\']+)["\']', attrs, re.I)
        if pm:
            permalink = _canonical_post_url(
                urljoin('https://www.reddit.com', pm.group(1))
            )
        if not permalink:
            tm = re.search(
                r'<a[^>]*class=["\'][^"\']*\btitle\b[^"\']*["\'][^>]*href=["\']([^"\']+)["\']',
                frag,
                re.I,
            )
            if tm:
                permalink = _canonical_post_url(
                    urljoin('https://www.reddit.com', tm.group(1))
                )
        if not permalink:
            continue

        title = None
        tm = re.search(
            r'<a[^>]*class=["\'][^"\']*\btitle\b[^"\']*["\'][^>]*>(.*?)</a>',
            frag,
            re.DOTALL | re.I,
        )
        if tm:
            title = _strip_tags(tm.group(1)) or None

        subreddit = None
        sm = re.search(r'data-subreddit=["\']([^"\']+)["\']', attrs, re.I)
        if sm:
            subreddit = sm.group(1)
        else:
            sm = re.search(
                r'class=["\'][^"\']*\bsubreddit\b[^"\']*["\'][^>]*>\s*r/([^<\s]+)',
                frag,
                re.I,
            )
            if sm:
                subreddit = sm.group(1)
            else:
                path_m = re.search(r'/r/([^/]+)/comments/', permalink)
                if path_m:
                    subreddit = path_m.group(1)

        score = None
        scm = re.search(r'data-score=["\'](-?\d+)["\']', attrs, re.I)
        if scm:
            score = int(scm.group(1))
        else:
            scm = re.search(
                r'class=["\'][^"\']*\bscore\b[^"\']*["\'][^>]*title=["\'](-?\d+)["\']',
                frag,
                re.I,
            )
            if scm:
                score = int(scm.group(1))

        items.append({
            'post_url': permalink,
            'title': title,
            'subreddit': subreddit,
            'date': _date_from_fragment(frag),
            'body': _body_from_thing(frag),
            'score': score,
            'comments': [],
        })
        if len(items) >= max_posts:
            break

    return items[:max_posts]


def parse_comments_from_html(html: str) -> list:
    """Harvest comment authors from an old.reddit comments page."""
    comments = []
    seen = set()

    for m in re.finditer(
        r'<div([^>]*\bthing\b[^>]*\bcomment\b[^>]*)>(.*?)(?=<div[^>]*\bthing\b|\Z)',
        html,
        re.DOTALL | re.I,
    ):
        attrs, body = m.group(1), m.group(2)
        frag = attrs + body

        name = None
        am = re.search(r'data-author=["\']([^"\']+)["\']', attrs, re.I)
        if am:
            name = am.group(1)
        else:
            am = re.search(
                r'<a[^>]*class=["\'][^"\']*\bauthor\b[^"\']*["\'][^>]*>\s*([^<\s]+)',
                frag,
                re.I,
            )
            if am:
                name = unescape(am.group(1).strip())

        if not name or name.lower() in ('[deleted]', 'automoderator'):
            continue

        text = _body_from_thing(frag) or ''
        key = (name, text)
        if key in seen:
            continue
        seen.add(key)

        comments.append({
            'name': name,
            'profile_url': _user_profile_url(name),
            'comment_text': text,
        })

    return comments


def parse_submission_page_from_html(html: str, post_url: str) -> dict:
    """Parse a single submission page; merge list fields + comments."""
    if _looks_like_login_page(html):
        raise RuntimeError(
            "Reddit login page detected — cookies missing or session expired."
        )

    title = None
    tm = re.search(
        r'<a[^>]*class=["\'][^"\']*\btitle\b[^"\']*["\'][^>]*>\s*(.*?)</a>',
        html,
        re.DOTALL | re.I,
    )
    if tm:
        title = _strip_tags(tm.group(1)) or None

    subreddit = None
    sm = re.search(r'data-subreddit=["\']([^"\']+)["\']', html, re.I)
    if sm:
        subreddit = sm.group(1)
    else:
        path_m = re.search(r'/r/([^/]+)/comments/', post_url)
        if path_m:
            subreddit = path_m.group(1)

    score = None
    scm = re.search(r'data-score=["\'](-?\d+)["\']', html, re.I)
    if scm:
        score = int(scm.group(1))

    body = None
    lm = re.search(
        r'<div[^>]*class=["\'][^"\']*\bthing\b[^"\']*\blink\b[^"\']*["\'][^>]*>'
        r'(.*?)(?=<div[^>]*\bthing\b[^>]*\bcomment\b|$)',
        html,
        re.DOTALL | re.I,
    )
    if lm:
        body = _body_from_thing(lm.group(1))
    if body is None:
        body = _body_from_thing(html)

    return {
        'post_url': post_url,
        'title': title,
        'subreddit': subreddit,
        'date': _date_from_fragment(html),
        'body': body,
        'score': score,
        'comments': parse_comments_from_html(html),
    }


def _submitted_url(profile_url: str) -> str:
    name = _username_from_url(profile_url)
    if not name:
        raise ValueError(f"Cannot derive Reddit username from: {profile_url}")
    return f'https://old.reddit.com/user/{name}/submitted/'


def phase1_collect_submissions(sb, profile_url: str, max_posts: int) -> list:
    print(f"\nPHASE 1 — Collecting up to {max_posts} submissions")
    url = _submitted_url(profile_url)
    sb.open(url)
    time.sleep(4)
    html = sb.get_page_source()
    if _looks_like_login_page(html):
        raise RuntimeError(
            "Reddit login page detected after cookie load — "
            "session expired or cookies invalid."
        )

    items = parse_submissions_list_from_html(html, max_posts=max_posts)
    for _ in range(3):
        if len(items) >= max_posts:
            break
        sb.execute_script("(function(){ window.scrollBy(0, 1200); })()")
        time.sleep(2)
        html = sb.get_page_source()
        items = parse_submissions_list_from_html(html, max_posts=max_posts)

    print(f"   Found {len(items)} submissions")
    return items


def phase2_scrape_comments(sb, item: dict, idx: int, total: int) -> dict:
    post_url = item['post_url']
    old_url = _to_old_reddit(post_url)
    print(f"\n  [{idx}/{total}] {post_url}")
    sb.open(old_url)
    time.sleep(3)
    html = sb.get_page_source()
    try:
        parsed = parse_submission_page_from_html(html, post_url)
    except Exception as e:
        print(f"    Error parsing comments: {e}")
        item = dict(item)
        item['comments'] = []
        item['error'] = str(e)
        return item

    out = {
        'post_url': post_url,
        'title': parsed.get('title') or item.get('title'),
        'subreddit': parsed.get('subreddit') or item.get('subreddit'),
        'date': parsed.get('date') or item.get('date'),
        'body': parsed.get('body') if parsed.get('body') is not None else item.get('body'),
        'score': parsed.get('score') if parsed.get('score') is not None else item.get('score'),
        'comments': parsed.get('comments') or [],
    }
    print(f"    title   : {(out.get('title') or '')[:60]}")
    print(f"    comments: {len(out.get('comments') or [])}")
    return out


def main(PROFILE_URL: str, MAX_POSTS: int = 10):
    """
    Live scrape Reddit submissions + comments → ``reddit_submissions.json``.

    Prefer old.reddit.com. NOTE: selectors may need live tuning.
    """
    print("\n" + "═" * 65)
    print("Reddit Submissions Scraper")
    print(f"Profile: {PROFILE_URL}  max={MAX_POSTS}")
    print("═" * 65)

    _require_cookies()
    results = []

    with SB(uc=True, headless=False, xvfb=True, window_size="1280,900") as sb:
        login(sb)
        items = phase1_collect_submissions(sb, PROFILE_URL, MAX_POSTS)

        print(f"\n{'═'*65}")
        print(f"PHASE 2 — Scraping comments for {len(items)} posts")
        print("═" * 65)

        for i, item in enumerate(items, 1):
            try:
                results.append(phase2_scrape_comments(sb, item, i, len(items)))
            except Exception as e:
                print(f"    Error on post {i}: {e}")
                err = dict(item)
                err['comments'] = err.get('comments') or []
                err['error'] = str(e)
                results.append(err)
            time.sleep(2)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n Saved to {OUTPUT_FILE} ({len(results)} submissions)")
    return results


if __name__ == "__main__":
    import sys
    url = sys.argv[1] if len(sys.argv) > 1 else input("Profile URL: ").strip()
    main(url)
