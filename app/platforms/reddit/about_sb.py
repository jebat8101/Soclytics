"""
Reddit profile (about) scraper via SeleniumBase.

Prefers ``old.reddit.com`` HTML (titlebox karma / cake day).
Requires ``platforms.reddit.constants.COOKIE_FILE`` (pickle cookies).
Raises if the cookie file is missing or a login wall is detected.
"""
from seleniumbase import SB
import pickle
import time
import os
import subprocess
import json
import re
from html import unescape
from urllib.parse import urlparse

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

from platforms.reddit.constants import COOKIE_FILE

OUTPUT_FILE = "reddit_about.json"
PROFILE_URL = "https://www.reddit.com/user/"


def _require_cookies():
    if not os.path.exists(COOKIE_FILE):
        raise FileNotFoundError(
            f"Reddit cookie file missing: {COOKIE_FILE}. "
            "Import/export cookies before scraping."
        )


def _looks_like_login_page(html: str) -> bool:
    lower = (html or '').lower()
    if 'www.reddit.com/login' in lower or 'old.reddit.com/login' in lower:
        if 'titlebox' not in lower and 'thing link' not in lower:
            return True
    login_markers = (
        'log in to reddit',
        'name="user"',
        'id="login-username"',
        'data-testid="login-button"',
    )
    has_login = any(x in lower for x in login_markers)
    has_profile = 'titlebox' in lower or 'class="karma"' in lower
    return has_login and not has_profile


def _to_old_reddit(url: str) -> str:
    if not url:
        return url
    return (
        url.replace('https://www.reddit.com', 'https://old.reddit.com')
        .replace('http://www.reddit.com', 'https://old.reddit.com')
        .replace('https://reddit.com', 'https://old.reddit.com')
        .replace('http://reddit.com', 'https://old.reddit.com')
    )


def _username_from_url(profile_url: str):
    path = urlparse(profile_url).path.strip('/')
    parts = [p for p in path.split('/') if p]
    if len(parts) >= 2 and parts[0] in ('user', 'u'):
        return parts[1]
    if len(parts) == 1:
        return parts[0]
    return None


def login(sb):
    """Load Reddit cookies into the browser session."""
    _require_cookies()
    sb.open("https://old.reddit.com/")
    time.sleep(2)
    with open(COOKIE_FILE, "rb") as f:
        cookies = pickle.load(f)
    for c in cookies:
        try:
            cookie = dict(c)
            domain = cookie.get('domain') or '.reddit.com'
            if 'reddit.com' not in str(domain):
                cookie['domain'] = '.reddit.com'
            sb.driver.add_cookie(cookie)
        except Exception:
            pass
    sb.driver.refresh()
    time.sleep(3)
    print("Logged in")


def _field(field_type: str, label: str, value) -> dict:
    return {
        'field_type': field_type,
        'label': label,
        'value': '' if value is None else str(value),
    }


def parse_profile_from_html(html: str, profile_url: str) -> dict:
    """
    Parse Reddit profile about fields from old.reddit.com HTML (unit-testable).

    Returns a dict matching the Task 10 ``reddit_about.json`` contract.
    """
    if _looks_like_login_page(html):
        raise RuntimeError(
            "Reddit login page detected — cookies missing or session expired."
        )

    owner_name = _username_from_url(profile_url)
    is_locked = False
    post_karma = None
    comment_karma = None
    cake_day = None

    lower = html.lower()
    if any(
        x in lower
        for x in (
            'this account has been suspended',
            'has been banned from',
            'account deleted',
            "nobody on reddit goes by that name",
            'page not found',
        )
    ):
        is_locked = True

    m = re.search(
        r'<div[^>]*class=["\'][^"\']*titlebox[^"\']*["\'][^>]*>.*?<'
        r'h1[^>]*>\s*(?:<a[^>]*>)?\s*([^<\s]+)',
        html,
        re.DOTALL | re.I,
    )
    if m:
        owner_name = unescape(m.group(1).strip()) or owner_name

    m = re.search(
        r'title=["\']post karma["\'][^>]*>\s*([\d,]+)',
        html,
        re.I,
    )
    if not m:
        m = re.search(
            r'>([\d,]+)</span>\s*post karma',
            html,
            re.I,
        )
    if m:
        post_karma = m.group(1).replace(',', '')

    m = re.search(
        r'title=["\']comment karma["\'][^>]*>\s*([\d,]+)',
        html,
        re.I,
    )
    if not m:
        m = re.search(
            r'>([\d,]+)</span>\s*comment karma',
            html,
            re.I,
        )
    if m:
        comment_karma = m.group(1).replace(',', '')

    if post_karma is None:
        m = re.search(
            r'<span[^>]*class=["\'][^"\']*\bkarma\b[^"\']*["\'][^>]*>\s*([\d,]+)',
            html,
            re.I,
        )
        if m:
            post_karma = m.group(1).replace(',', '')

    m = re.search(
        r'<span[^>]*class=["\'][^"\']*\bage\b[^"\']*["\'][^>]*>.*?'
        r'<time[^>]+datetime=["\']([^"\']+)["\']',
        html,
        re.DOTALL | re.I,
    )
    if m:
        dm = re.match(r'(\d{4}-\d{2}-\d{2})', m.group(1))
        if dm:
            cake_day = dm.group(1)

    sections_profile = []
    if post_karma is not None:
        sections_profile.append(_field('karma', 'Post Karma', post_karma))
    if comment_karma is not None:
        sections_profile.append(
            _field('comment_karma', 'Comment Karma', comment_karma)
        )
    if cake_day is not None:
        sections_profile.append(_field('cake_day', 'Cake Day', cake_day))

    return {
        'profile_url': profile_url,
        'owner_name': owner_name,
        'is_locked': bool(is_locked),
        'sections': {
            'profile': sections_profile,
        },
    }


def main(PROFILE_URL: str = PROFILE_URL):
    """
    Live scrape Reddit profile about data → ``reddit_about.json``.

    Prefer old.reddit.com HTML. NOTE: selectors may need live tuning.
    """
    print("\n" + "═" * 65)
    print("Reddit About Scraper")
    print(f"Profile: {PROFILE_URL}")
    print("═" * 65)

    _require_cookies()
    old_url = _to_old_reddit(PROFILE_URL.rstrip('/') + '/')

    with SB(uc=True, headless=False, xvfb=True, window_size="1280,900") as sb:
        login(sb)
        print("\n   Opening profile (old.reddit.com)...")
        sb.open(old_url)
        time.sleep(4)
        html = sb.get_page_source()
        if _looks_like_login_page(html):
            raise RuntimeError(
                "Reddit login page detected after cookie load — "
                "session expired or cookies invalid."
            )
        output = parse_profile_from_html(html, PROFILE_URL)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n   Owner    : {output.get('owner_name')}")
    print(f"   Locked   : {output.get('is_locked')}")
    print(f"   Fields   : {len(output.get('sections', {}).get('profile', []))}")
    print(f"\n Saved to {OUTPUT_FILE}")
    return output


if __name__ == "__main__":
    main()
