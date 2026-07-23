import re
from urllib.parse import urlparse

_IG_USER = re.compile(r'^[A-Za-z0-9._]{1,30}$')
_RD_USER = re.compile(r'^[A-Za-z0-9_-]{3,20}$')

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
