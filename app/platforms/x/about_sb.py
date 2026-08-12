"""X.com profile about scraper via SeleniumBase.

Parses og meta tags and data-testid DOM fallbacks. Counts-only module —
no follower lists.
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

from platforms.x.constants import COOKIE_FILE

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

OUTPUT_FILE = 'x_about.json'
PROFILE_URL = 'https://x.com/example'
X_HOME = 'https://x.com/'


def _require_cookies():
    if not os.path.exists(COOKIE_FILE):
        raise FileNotFoundError(
            f'X cookie file missing: {COOKIE_FILE}. '
            'Import/export cookies before scraping.'
        )


def _looks_like_login_page(html: str, current_url: str = '') -> bool:
    url = (current_url or '').lower()
    if '/i/flow/login' in url or url.rstrip('/').endswith('/login'):
        return True
    lower = (html or '').lower()
    has_profile_signal = (
        ('og:title' in lower and '@' in lower)
        or 'data-testid="username"' in lower
        or 'data-testid="userdescription"' in lower
        or 'data-testid="usernamelink"' in lower
    )
    if has_profile_signal:
        return False
    return any(
        x in lower
        for x in (
            'sign in to x',
            'log in to x',
            'sign in to twitter',
            'name="password"',
            'aria-label="password"',
        )
    )


def login(sb):
    _require_cookies()
    sb.open(X_HOME)
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


def _handle_from_url(profile_url: str) -> str | None:
    path = urlparse(profile_url).path.strip('/')
    if not path:
        return None
    first = path.split('/')[0]
    if first.startswith('@'):
        first = first[1:]
    return first or None


def parse_profile_from_html(html: str, profile_url: str) -> dict:
    username = _handle_from_url(profile_url)
    owner_name = None
    bio = None
    website = None
    followers = None
    following = None
    profile_pic = None
    is_verified = False
    is_locked = False

    og_title = _meta_content(html, prop='og:title') or ''
    desc = _meta_content(html, name='description') or _meta_content(html, prop='og:description') or ''
    og_image = _meta_content(html, prop='og:image')

    title_match = re.match(r'^(.*?)\s*\(@([^)]+)\)', og_title)
    if title_match:
        owner_name = title_match.group(1).strip() or None
        username = username or title_match.group(2).strip()

    name_block = re.search(
        r'data-testid=["\']UserName["\'][^>]*>(.*?)</div>\s*</div>',
        html,
        re.I | re.DOTALL,
    )
    if name_block and not owner_name:
        texts = re.findall(r'>([^<]{1,80})<', name_block.group(1))
        texts = [t.strip() for t in texts if t.strip() and not t.strip().startswith('@')]
        if texts:
            owner_name = texts[0]

    handle_m = re.search(r'data-testid=["\']UserName["\'][^>]*>.*?@([A-Za-z0-9_]{1,15})', html, re.I | re.DOTALL)
    if handle_m:
        username = username or handle_m.group(1)

    bio_m = re.search(
        r'data-testid=["\']UserDescription["\'][^>]*>(.*?)</div>',
        html,
        re.I | re.DOTALL,
    )
    if bio_m:
        bio_text = re.sub(r'<[^>]+>', '', bio_m.group(1))
        bio = unescape(re.sub(r'\s+', ' ', bio_text)).strip() or None
    if not bio and desc and 'on X:' not in desc:
        bio = desc.strip() or None

    if og_image:
        profile_pic = og_image

    fol_m = re.search(
        r'href=["\'][^"\']*/(?:verified_)?followers["\'][^>]*>.*?>([\d.,KMB]+)<',
        html,
        re.I | re.DOTALL,
    )
    if fol_m:
        followers = _parse_int(fol_m.group(1))
    if followers is None:
        fol_m = re.search(r'([\d.,KMB]+)\s+Followers?', html, re.I)
        if fol_m:
            followers = _parse_int(fol_m.group(1))

    fing_m = re.search(
        r'href=["\'][^"\']*/following["\'][^>]*>.*?>([\d.,KMB]+)<',
        html,
        re.I | re.DOTALL,
    )
    if fing_m:
        following = _parse_int(fing_m.group(1))
    if following is None:
        fing_m = re.search(r'([\d.,KMB]+)\s+Following', html, re.I)
        if fing_m:
            following = _parse_int(fing_m.group(1))

    lower = html.lower()
    if any(x in lower for x in (
        'this account is protected',
        'these posts are protected',
        'this account\'s posts are protected',
    )):
        is_locked = True
    if 'verified' in lower and ('data-testid="icon-verified"' in lower or 'aria-label="verified"' in lower):
        is_verified = True

    url_m = re.search(r'data-testid=["\']UserUrl["\'][^>]*>.*?href=["\']([^"\']+)["\']', html, re.I | re.DOTALL)
    if url_m:
        website = unescape(url_m.group(1))

    profile_fields = []
    if username:
        profile_fields.append(_field('username', 'Username', f'@{username}'))
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
        'owner_name': owner_name or username,
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
    print('X About Scraper')
    print(f'Profile: {PROFILE_URL}')
    print('═' * 65)

    _require_cookies()
    with SB(uc=True, headless=False, xvfb=True, window_size='1280,900') as sb:
        login(sb)
        sb.open(PROFILE_URL)
        time.sleep(6)
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
