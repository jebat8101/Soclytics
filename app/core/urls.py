import re
from urllib.parse import urlparse, unquote

_IG_USER = re.compile(r'^[A-Za-z0-9._]{1,30}$')
_RD_USER = re.compile(r'^[A-Za-z0-9_-]{3,20}$')
_TH_USER = re.compile(r'^[A-Za-z0-9._]{1,30}$')
_TG_USER = re.compile(r'^[A-Za-z0-9_]{4,32}$')
_X_USER = re.compile(r'^[A-Za-z0-9_]{1,15}$')
_X_RESERVED = {
    'home', 'explore', 'search', 'i', 'settings', 'messages', 'notifications',
    'compose', 'login', 'intent', 'hashtag', 'tos', 'privacy', 'about',
    'download', 'jobs', 'help', 'signup', 'share', 'status', 'hashtags',
    'lists', 'communities', 'connect_people', 'following', 'followers',
}

def normalize_instagram_target(raw: str) -> str:
    s = (raw or '').strip()
    if not s:
        raise ValueError('empty Instagram target')
    if s.startswith('@'):
        s = s[1:]
    if '://' not in s and '/' not in s:
        if not _IG_USER.match(s):
            raise ValueError(f'invalid Instagram username: {s}')
        return f'https://www.instagram.com/{s}/'
    u = urlparse(s if '://' in s else 'https://' + s)
    host = (u.hostname or '').lower().replace('www.', '')
    if host not in ('instagram.com',):
        raise ValueError('not an Instagram URL')
    parts = [p for p in u.path.split('/') if p]
    reserved = {'p', 'reel', 'reels', 'stories', 'explore', 'accounts', 'direct'}
    if not parts or parts[0].lower() in reserved:
        raise ValueError('Instagram target must be a profile URL or username')
    user = parts[0]
    if not _IG_USER.match(user):
        raise ValueError(f'invalid Instagram username: {user}')
    return f'https://www.instagram.com/{user}/'

def normalize_reddit_target(raw: str) -> str:
    s = (raw or '').strip()
    if not s:
        raise ValueError('empty Reddit target')
    if s.lower().startswith('u/'):
        s = s[2:]
    if '://' not in s and '/' not in s:
        if not _RD_USER.match(s):
            raise ValueError(f'invalid Reddit username: {s}')
        return f'https://www.reddit.com/user/{s}/'
    u = urlparse(s if '://' in s else 'https://' + s)
    host = (u.hostname or '').lower()
    if host not in ('reddit.com', 'www.reddit.com', 'old.reddit.com', 'www.old.reddit.com'):
        raise ValueError('not a Reddit URL')
    parts = [p for p in u.path.split('/') if p]
    if len(parts) >= 2 and parts[0].lower() in ('user', 'u'):
        name = parts[1]
        if not _RD_USER.match(name):
            raise ValueError(f'invalid Reddit username: {name}')
        return f'https://www.reddit.com/user/{name}/'
    raise ValueError('Reddit target must be a user profile')

def normalize_threads_target(raw: str) -> str:
    s = (raw or '').strip()
    if not s:
        raise ValueError('empty Threads target')
    if s.startswith('@'):
        s = s[1:]
    if '://' not in s and '/' not in s:
        if not _TH_USER.match(s):
            raise ValueError(f'invalid Threads username: {s}')
        return f'https://www.threads.com/@{s}/'
    u = urlparse(s if '://' in s else 'https://' + s)
    host = (u.hostname or '').lower().replace('www.', '')
    if host not in ('threads.com', 'threads.net'):
        raise ValueError('not a Threads URL')
    parts = [p for p in u.path.split('/') if p]
    if not parts:
        raise ValueError('Threads target must be a profile URL or username')
    first = parts[0]
    if not first.startswith('@'):
        raise ValueError('Threads target must be a profile URL or username')
    user = first[1:]
    if not _TH_USER.match(user):
        raise ValueError(f'invalid Threads username: {user}')
    if len(parts) > 1:
        raise ValueError('Threads target must be a profile URL, not a post URL')
    return f'https://www.threads.com/@{user}/'


def normalize_x_target(raw: str) -> str:
    s = (raw or '').strip()
    if not s:
        raise ValueError('empty X target')
    if s.startswith('@'):
        s = s[1:]
    if '://' not in s and '/' not in s:
        if not _X_USER.match(s):
            raise ValueError(f'invalid X username: {s}')
        return f'https://x.com/{s}'
    u = urlparse(s if '://' in s else 'https://' + s)
    host = (u.hostname or '').lower().replace('www.', '')
    if host not in ('x.com', 'twitter.com', 'mobile.twitter.com', 'mobile.x.com'):
        raise ValueError('not an X / Twitter URL')
    parts = [p for p in u.path.split('/') if p]
    if not parts or parts[0].lower() in _X_RESERVED:
        raise ValueError('X target must be a profile URL or username')
    if any(p.lower() == 'status' for p in parts):
        raise ValueError('X target must be a profile URL, not a status URL')
    user = parts[0]
    if user.startswith('@'):
        user = user[1:]
    if not _X_USER.match(user):
        raise ValueError(f'invalid X username: {user}')
    return f'https://x.com/{user}'


def extract_telegram_username(url: str) -> str | None:
    """Parse a public @username from t.me links, bare @user, or t.me/s/user."""
    url = (url or '').strip()
    if not url.startswith(('http://', 'https://')):
        bare = url[1:] if url.startswith('@') else url
        if _TG_USER.fullmatch(bare):
            return bare
        url = 'https://' + url
    path = unquote(urlparse(url).path).strip('/')
    if not path:
        return None
    parts = path.split('/')
    first = parts[0]
    if first == 's' and len(parts) > 1:
        first = parts[1]
    if first.startswith('@'):
        first = first[1:]
    if first.startswith('+') or first in (
        'joinchat', 'c', 'share', 'addstickers', 'proxy', 'socks', 'login', 'iv',
    ):
        return None
    if _TG_USER.fullmatch(first):
        return first
    return None


def normalize_telegram_target(raw: str) -> str:
    s = (raw or '').strip()
    if not s:
        raise ValueError('empty Telegram target')
    username = extract_telegram_username(s)
    if not username:
        raise ValueError(
            'Telegram invite links have no public username — use t.me/<channel> or @name'
        )
    return f'https://t.me/{username}'
