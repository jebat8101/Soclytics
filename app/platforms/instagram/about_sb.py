"""
Instagram profile (about) scraper via SeleniumBase.

Selectors and embedded JSON shapes are best-effort against Instagram's
current DOM/meta markup and may need live tuning when IG changes markup.

Requires ``platforms.instagram.constants.COOKIE_FILE`` (pickle cookies).
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

from platforms.instagram.constants import COOKIE_FILE

OUTPUT_FILE = "ig_about.json"
PROFILE_URL = "https://www.instagram.com/"


def _require_cookies():
    if not os.path.exists(COOKIE_FILE):
        raise FileNotFoundError(
            f"Instagram cookie file missing: {COOKIE_FILE}. "
            "Import/export cookies before scraping."
        )


def _looks_like_login_page(html: str) -> bool:
    lower = (html or '').lower()
    if 'accounts/login' in lower:
        return True
    has_login = any(
        x in lower
        for x in ('name="username"', 'name="password"', 'log in to instagram')
    )
    has_profile = 'og:title' in lower and '@' in lower
    return has_login and not has_profile


def login(sb):
    """Load Instagram cookies into the browser session."""
    _require_cookies()
    sb.open("https://www.instagram.com/")
    time.sleep(3)
    with open(COOKIE_FILE, "rb") as f:
        cookies = pickle.load(f)
    for c in cookies:
        try:
            sb.driver.add_cookie(c)
        except Exception:
            pass
    sb.driver.refresh()
    time.sleep(5)
    print("Logged in")


def _username_from_url(profile_url: str):
    path = urlparse(profile_url).path.strip('/')
    if not path:
        return None
    part = path.split('/')[0]
    if part in ('p', 'reel', 'reels', 'stories', 'explore', 'accounts'):
        return None
    return part or None


def _parse_int(val):
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return int(val)
    s = str(val).strip().replace(',', '').replace(' ', '')
    m = re.match(r'^([\d.]+)\s*([kmb])?$', s, re.I)
    if not m:
        digits = re.sub(r'[^\d]', '', s)
        return int(digits) if digits else None
    num = float(m.group(1))
    suffix = (m.group(2) or '').lower()
    mult = {'k': 1_000, 'm': 1_000_000, 'b': 1_000_000_000}.get(suffix, 1)
    return int(num * mult)


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


def _find_user_dict(obj, depth=0):
    if depth > 12 or obj is None:
        return None
    if isinstance(obj, dict):
        if 'username' in obj and (
            'biography' in obj
            or 'edge_followed_by' in obj
            or 'full_name' in obj
        ):
            return obj
        try:
            user = obj['entry_data']['ProfilePage'][0]['graphql']['user']
            if isinstance(user, dict) and 'username' in user:
                return user
        except (KeyError, IndexError, TypeError):
            pass
        for v in obj.values():
            found = _find_user_dict(v, depth + 1)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _find_user_dict(item, depth + 1)
            if found:
                return found
    return None


def _extract_shared_user(html: str):
    """Best-effort extract of ProfilePage user object from embedded JSON."""
    blobs = []
    m = re.search(r'window\._sharedData\s*=\s*(\{.+?\});', html, re.DOTALL)
    if m:
        blobs.append(m.group(1))

    for sm in re.finditer(
        r'<script[^>]*type=["\']application/json["\'][^>]*>(.*?)</script>',
        html,
        re.DOTALL | re.I,
    ):
        blobs.append(sm.group(1).strip())

    for sm in re.finditer(
        r'<script[^>]*type=["\']text/javascript["\'][^>]*>(.*?)</script>',
        html,
        re.DOTALL | re.I,
    ):
        body = sm.group(1)
        if 'biography' in body or 'edge_followed_by' in body:
            blobs.append(body)

    for blob in blobs:
        try:
            data = json.loads(blob)
            user = _find_user_dict(data)
            if user:
                return user
        except (json.JSONDecodeError, TypeError):
            pass

        for jm in re.finditer(
            r'\{[^{}]*"username"\s*:\s*"[^"]+"[^{}]*\}', blob
        ):
            try:
                frag = json.loads(jm.group(0))
                if 'biography' in frag or 'full_name' in frag:
                    return frag
            except json.JSONDecodeError:
                continue

        user = {}
        for key, pat in (
            ('username', r'"username"\s*:\s*"([^"]+)"'),
            ('full_name', r'"full_name"\s*:\s*"([^"]*)"'),
            ('biography', r'"biography"\s*:\s*"((?:\\.|[^"\\])*)"'),
            ('external_url', r'"external_url"\s*:\s*"([^"]*)"'),
        ):
            mm = re.search(pat, blob)
            if mm:
                val = mm.group(1)
                try:
                    val = json.loads(f'"{val}"')
                except json.JSONDecodeError:
                    val = unescape(val.replace('\\/', '/'))
                user[key] = val
        for key, pat in (
            ('followers', r'"edge_followed_by"\s*:\s*\{\s*"count"\s*:\s*(\d+)'),
            ('following', r'"edge_follow"\s*:\s*\{\s*"count"\s*:\s*(\d+)'),
            (
                'post_count',
                r'"edge_owner_to_timeline_media"\s*:\s*\{\s*"count"\s*:\s*(\d+)',
            ),
        ):
            mm = re.search(pat, blob)
            if mm:
                user[key] = int(mm.group(1))
        mm = re.search(r'"is_private"\s*:\s*(true|false)', blob)
        if mm:
            user['is_private'] = mm.group(1) == 'true'
        if user.get('username') or user.get('biography'):
            return user
    return None


def _parse_meta_description_counts(desc: str) -> dict:
    out = {}
    if not desc:
        return out
    bio_m = re.match(
        r'^(.*?)\s*\d[\d,.]*\s*[KkMmBb]?\s*Followers',
        desc,
        re.I | re.DOTALL,
    )
    if bio_m:
        bio = bio_m.group(1).strip(' .')
        if bio and 'instagram' not in bio.lower():
            out['bio'] = bio

    for label, key in (
        ('Followers', 'followers'),
        ('Following', 'following'),
        ('Posts', 'post_count'),
    ):
        m = re.search(rf'([\d,.]+)\s*[KkMmBb]?\s*{label}', desc, re.I)
        if m:
            out[key] = _parse_int(m.group(1))
    return out


def _parse_og_title(title: str) -> dict:
    out = {}
    if not title:
        return out
    title = re.sub(r'\s*[•·].*$', '', title).strip()
    m = re.match(r'^(.+?)\s*\(@([^)]+)\)\s*$', title)
    if m:
        out['owner_name'] = m.group(1).strip()
        out['username'] = m.group(2).strip()
    elif title.startswith('@'):
        out['username'] = title[1:].strip()
    else:
        out['owner_name'] = title
    return out


def _dom_bio(html: str):
    m = re.search(
        r'<div[^>]*data-testid=["\']user-bio["\'][^>]*>(.*?)</div>',
        html,
        re.DOTALL | re.I,
    )
    if m:
        text = re.sub(r'<[^>]+>', '', m.group(1))
        return unescape(text).strip() or None
    return None


def _dom_website(html: str):
    m = re.search(
        r'<a[^>]+href=["\'](https?://[^"\']+)["\'][^>]*rel=["\'][^"\']*me[^"\']*["\']',
        html,
        re.I,
    )
    if m:
        return unescape(m.group(1)).strip()
    return None


def _field(field_type: str, label: str, value) -> dict:
    return {
        'field_type': field_type,
        'label': label,
        'value': '' if value is None else str(value),
    }


def parse_profile_from_html(html: str, profile_url: str) -> dict:
    """
    Parse Instagram profile fields from page HTML (unit-testable).

    Prefer embedded shared/JSON data, then og/meta tags, then light DOM hints.
    Returns a dict matching the Task 7 ``ig_about.json`` contract, including
    ``sections.profile`` field objects for DB import.
    """
    if _looks_like_login_page(html):
        raise RuntimeError(
            "Instagram login page detected — cookies missing or session expired."
        )

    username = _username_from_url(profile_url)
    owner_name = None
    bio = None
    website = None
    followers = None
    following = None
    post_count = None
    is_locked = False

    user = _extract_shared_user(html)
    if user:
        username = user.get('username') or username
        owner_name = user.get('full_name') or owner_name
        if user.get('biography') is not None:
            bio = user.get('biography')
        website = user.get('external_url') or website
        if 'edge_followed_by' in user and isinstance(user['edge_followed_by'], dict):
            followers = user['edge_followed_by'].get('count', followers)
        elif 'followers' in user:
            followers = user.get('followers', followers)
        if 'edge_follow' in user and isinstance(user['edge_follow'], dict):
            following = user['edge_follow'].get('count', following)
        elif 'following' in user:
            following = user.get('following', following)
        if 'edge_owner_to_timeline_media' in user and isinstance(
            user['edge_owner_to_timeline_media'], dict
        ):
            post_count = user['edge_owner_to_timeline_media'].get('count', post_count)
        elif 'post_count' in user:
            post_count = user.get('post_count', post_count)
        if user.get('is_private'):
            is_locked = True

    og = _parse_og_title(_meta_content(html, prop='og:title') or '')
    username = username or og.get('username')
    owner_name = owner_name or og.get('owner_name')

    desc = (
        _meta_content(html, name='description')
        or _meta_content(html, prop='og:description')
        or ''
    )
    meta_bits = _parse_meta_description_counts(desc)
    if bio is None:
        bio = meta_bits.get('bio')
    if followers is None:
        followers = meta_bits.get('followers')
    if following is None:
        following = meta_bits.get('following')
    if post_count is None:
        post_count = meta_bits.get('post_count')

    if bio is None:
        bio = _dom_bio(html)
    website = website or _dom_website(html)

    lower = html.lower()
    if 'this account is private' in lower or 'account is private' in lower:
        is_locked = True

    sections_profile = []
    if bio is not None and bio != '':
        sections_profile.append(_field('bio', 'Bio', bio))
    if website:
        sections_profile.append(_field('website', 'Website', website))
    if followers is not None:
        sections_profile.append(_field('followers', 'Followers', followers))
    if following is not None:
        sections_profile.append(_field('following', 'Following', following))
    if post_count is not None:
        sections_profile.append(_field('post_count', 'Posts', post_count))

    return {
        'profile_url': profile_url,
        'owner_name': owner_name,
        'username': username,
        'is_locked': bool(is_locked),
        'bio': bio,
        'website': website,
        'followers': followers,
        'following': following,
        'post_count': post_count,
        'sections': {
            'profile': sections_profile,
        },
    }


def main(PROFILE_URL: str = PROFILE_URL):
    """
    Live scrape Instagram profile about data → ``ig_about.json``.

    NOTE: DOM/meta/JSON selectors may need live tuning against authorized sessions.
    """
    print("\n" + "═" * 65)
    print("Instagram About Scraper")
    print(f"Profile: {PROFILE_URL}")
    print("═" * 65)

    _require_cookies()

    with SB(uc=True, headless=False, xvfb=True, window_size="1280,900") as sb:
        login(sb)
        print("\n   Opening profile...")
        sb.open(PROFILE_URL)
        time.sleep(6)
        html = sb.get_page_source()
        if _looks_like_login_page(html):
            raise RuntimeError(
                "Instagram login page detected after cookie load — "
                "session expired or cookies invalid."
            )
        output = parse_profile_from_html(html, PROFILE_URL)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n   Username : {output.get('username')}")
    print(f"   Owner    : {output.get('owner_name')}")
    print(f"   Bio      : {output.get('bio')}")
    print(f"   Locked   : {output.get('is_locked')}")
    print(f"\n Saved to {OUTPUT_FILE}")
    return output


if __name__ == "__main__":
    main()
