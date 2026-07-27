"""Threads profile about scraper via SeleniumBase.

Parses Meta ``data-sjs`` hydration JSON (user object with follower_count /
biography) with meta-tag and DOM fallbacks.
"""
import json
import os
import pickle
import re
import subprocess
import time
from html import unescape
from urllib.parse import urlparse

from seleniumbase import SB

from platforms.threads.constants import COOKIE_FILE

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

OUTPUT_FILE = 'threads_about.json'
PROFILE_URL = 'https://www.threads.com/@example/'


def _require_cookies():
    if not os.path.exists(COOKIE_FILE):
        raise FileNotFoundError(
            f'Threads cookie file missing: {COOKIE_FILE}. '
            'Import/export cookies before scraping.'
        )


def _looks_like_login_page(html: str) -> bool:
    """Return True only for real login walls.

    Threads SPA HTML often embeds ``/login`` routes in JS bundles even when
    the operator is authenticated, so substring checks on ``/login`` alone
    cause false aborts and empty investigations.
    """
    lower = (html or '').lower()
    has_profile_signal = (
        ('og:title' in lower and '@' in lower)
        or 'follower_count' in lower
        or 'thread_items' in lower
        or 'biography' in lower
    )
    if has_profile_signal:
        return False
    has_login_form = any(
        x in lower
        for x in (
            'log in to threads',
            'log into threads',
            'name="username"',
            'name="password"',
            'aria-label="password"',
        )
    )
    return has_login_form


def login(sb):
    _require_cookies()
    sb.open('https://www.threads.com/')
    time.sleep(3)
    with open(COOKIE_FILE, 'rb') as f:
        cookies = pickle.load(f)
    added = 0
    for c in cookies:
        try:
            sc = {
                k: c[k]
                for k in ('name', 'value', 'domain', 'path', 'secure', 'httpOnly')
                if k in c and c[k] is not None
            }
            if not sc.get('path'):
                sc['path'] = '/'
            expires = c.get('expiry') or c.get('expires') or c.get('expirationDate')
            if expires and isinstance(expires, (int, float)):
                sc['expiry'] = int(expires)
            sb.driver.add_cookie(sc)
            added += 1
        except Exception as e:
            print(f'  cookie skip {c.get("name")}: {e}')
    sb.driver.refresh()
    time.sleep(5)
    print(f'Logged in ({added}/{len(cookies)} cookies)')


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


def _field(field_type: str, label: str, value) -> dict:
    return {
        'field_type': field_type,
        'label': label,
        'value': '' if value is None else str(value),
    }


def _nested_lookup(key: str, obj, results=None):
    if results is None:
        results = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                results.append(v)
            _nested_lookup(key, v, results)
    elif isinstance(obj, list):
        for item in obj:
            _nested_lookup(key, item, results)
    return results


def _extract_sjs_blobs(html: str) -> list:
    blobs = []
    for match in re.finditer(
        r'<script[^>]*type=["\']application/json["\'][^>]*>(.*?)</script>',
        html,
        re.DOTALL | re.I,
    ):
        text = match.group(1).strip()
        if text:
            blobs.append(text)
    for match in re.finditer(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        re.DOTALL | re.I,
    ):
        text = match.group(1).strip()
        if text:
            blobs.append(text)
    return blobs


def _pick_user_dict(candidates: list) -> dict | None:
    best = None
    best_score = -1
    for item in candidates:
        if not isinstance(item, dict):
            continue
        if 'username' not in item:
            continue
        score = 0
        for key in (
            'follower_count',
            'biography',
            'full_name',
            'hd_profile_pic_versions',
            'profile_pic_url',
            'text_post_app_is_private',
            'bio_links',
        ):
            if key in item:
                score += 1
        if score > best_score:
            best_score = score
            best = item
    return best if best_score > 0 else None


def _profile_pic_from_user(user: dict):
    versions = user.get('hd_profile_pic_versions') or []
    if isinstance(versions, list) and versions:
        last = versions[-1]
        if isinstance(last, dict) and last.get('url'):
            return last['url']
    return user.get('profile_pic_url') or user.get('profile_pic')


def _website_from_user(user: dict):
    links = user.get('bio_links') or []
    if isinstance(links, list):
        for link in links:
            if isinstance(link, dict) and link.get('url'):
                return link['url']
            if isinstance(link, str) and link.startswith('http'):
                return link
    return user.get('external_url') or user.get('website')


def parse_profile_from_html(html: str, profile_url: str) -> dict:
    username = None
    owner_name = None
    bio = None
    website = None
    followers = None
    following = None
    profile_pic = None
    is_verified = False
    is_locked = False

    path = urlparse(profile_url).path.strip('/')
    if path.startswith('@'):
        username = path.split('/')[0][1:]

    for blob in _extract_sjs_blobs(html):
        if 'follower_count' not in blob and 'biography' not in blob:
            continue
        try:
            data = json.loads(blob)
        except json.JSONDecodeError:
            continue
        user = _pick_user_dict(_nested_lookup('user', data))
        if not user:
            # Walk for any dict that looks like a profile.
            stack = [data]
            while stack and not user:
                cur = stack.pop()
                if isinstance(cur, dict):
                    if 'username' in cur and (
                        'follower_count' in cur or 'biography' in cur
                    ):
                        user = cur
                        break
                    stack.extend(cur.values())
                elif isinstance(cur, list):
                    stack.extend(cur)
        if not user:
            continue

        username = user.get('username') or username
        owner_name = user.get('full_name') or user.get('name') or owner_name
        bio = user.get('biography') or user.get('bio') or bio
        website = _website_from_user(user) or website
        followers = user.get('follower_count') or user.get('followers_count') or followers
        following = user.get('following_count') or user.get('follow_count') or following
        profile_pic = _profile_pic_from_user(user) or profile_pic
        if user.get('is_verified'):
            is_verified = True
        if user.get('text_post_app_is_private') or user.get('is_private') or user.get('private'):
            is_locked = True
        break

    og_title = _meta_content(html, prop='og:title') or ''
    desc = _meta_content(html, name='description') or _meta_content(html, prop='og:description') or ''
    og_image = _meta_content(html, prop='og:image')

    if not owner_name:
        title_match = re.match(r'^(.*?)\s*\(@([^)]+)\)', og_title)
        if title_match:
            owner_name = title_match.group(1).strip() or None
            username = username or title_match.group(2).strip()

    if not bio and desc:
        bio_match = re.search(r'Bio:\s*(.+?)(?:\s+[A-Z][a-z]+ers?:|\s*$)', desc)
        if bio_match:
            bio = bio_match.group(1).strip(' .')

    if followers is None:
        match = re.search(r'Followers?:\s*([\d.,KMBkmb]+)', desc)
        if match:
            followers = _parse_int(match.group(1))
    if following is None:
        match = re.search(r'Following:\s*([\d.,KMBkmb]+)', desc)
        if match:
            following = _parse_int(match.group(1))

    if not profile_pic and og_image:
        profile_pic = og_image

    lower = html.lower()
    if 'private profile' in lower or 'this profile is private' in lower:
        is_locked = True

    profile_fields = []
    if bio:
        profile_fields.append(_field('bio', 'Bio', bio))
    if website:
        profile_fields.append(_field('website', 'Website', website))
    if followers is not None:
        profile_fields.append(_field('followers', 'Followers', followers))
    if following is not None:
        profile_fields.append(_field('following', 'Following', following))
    if profile_pic:
        profile_fields.append(_field('profile_pic', 'Profile Picture', profile_pic))
    if is_verified:
        profile_fields.append(_field('verified', 'Verified', 'true'))

    return {
        'profile_url': profile_url,
        'owner_name': owner_name,
        'username': username,
        'is_locked': bool(is_locked),
        'is_verified': bool(is_verified),
        'bio': bio,
        'website': website,
        'followers': followers,
        'following': following,
        'profile_pic': profile_pic,
        'sections': {'profile': profile_fields},
    }


def main(PROFILE_URL: str = PROFILE_URL):
    print('\n' + '═' * 65)
    print('Threads About Scraper')
    print(f'Profile: {PROFILE_URL}')
    print('═' * 65)

    _require_cookies()
    with SB(uc=True, headless=False, xvfb=True, window_size='1280,900') as sb:
        login(sb)
        sb.open(PROFILE_URL)
        time.sleep(6)
        html = sb.get_page_source()
        if _looks_like_login_page(html):
            raise RuntimeError(
                'Threads login page detected — cookies missing or session expired.'
            )
        output = parse_profile_from_html(html, PROFILE_URL)

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n   Username : {output.get('username')}")
    print(f"   Owner    : {output.get('owner_name')}")
    print(f"   Bio      : {output.get('bio')}")
    print(f"   Followers: {output.get('followers')}")
    print(f"   Locked   : {output.get('is_locked')}")
    print(f'\n Saved to {OUTPUT_FILE}')
    return output


if __name__ == '__main__':
    main()
