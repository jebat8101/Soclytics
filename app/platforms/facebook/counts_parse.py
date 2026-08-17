import re
from core.counts import parse_compact_int

_COUNT = re.compile(
    r'(\d[\d,]*(?:\.\d+)?)\s*([KMB])?\s*'
    r'(All reactions|reactions?|comments?|shares?|reposts?)',
    re.I,
)
_COUNT_LABEL_FIRST = re.compile(
    r'(All reactions|reactions?|comments?|shares?|reposts?)\s*:?\s*'
    r'(\d[\d,]*(?:\.\d+)?)\s*([KMB])?',
    re.I,
)


def _assign_count(out, kind, n):
    kind = kind.lower()
    if 'reaction' in kind:
        out['like_count'] = n
    elif 'comment' in kind:
        out['reply_count'] = n
    elif 'share' in kind or 'repost' in kind:
        out['repost_count'] = n


def parse_facebook_engagement(html: str) -> dict:
    out = {'like_count': 0, 'reply_count': 0, 'repost_count': 0}
    text = html or ''
    for match in _COUNT.finditer(text):
        n = parse_compact_int(match.group(1), match.group(2))
        if n is None:
            continue
        _assign_count(out, match.group(3), n)
    for match in _COUNT_LABEL_FIRST.finditer(text):
        n = parse_compact_int(match.group(2), match.group(3))
        if n is None:
            continue
        _assign_count(out, match.group(1), n)
    return out
