import re

ENGAGEMENT_COLS = ('like_count', 'reply_count', 'repost_count')


def parse_compact_int(num, suffix=None):
    if num is None:
        return None
    s = str(num).strip().replace(',', '').replace('\u00a0', '').replace(' ', '')
    if not s or s in {'.', ','}:
        return None
    match = re.match(r'^(\d*\.?\d+)\s*([kmb])?$', s, re.I)
    if match:
        try:
            value = float(match.group(1))
        except ValueError:
            return None
        suf = (match.group(2) or suffix or '').lower()
        return int(value * {'k': 1_000, 'm': 1_000_000, 'b': 1_000_000_000}.get(suf, 1))
    digits = re.sub(r'[^\d]', '', s)
    return int(digits) if digits else None


def as_int(value, default=0):
    if value is None or value == '':
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    parsed = parse_compact_int(str(value))
    return default if parsed is None else parsed


def ensure_engagement_columns(con, tables=('photo_posts', 'reel_posts', 'text_posts')):
    cur = con.cursor()
    for table in tables:
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        )
        if not cur.fetchone():
            continue
        cur.execute(f'PRAGMA table_info({table})')
        cols = {row[1] for row in cur.fetchall()}
        for col in ENGAGEMENT_COLS:
            if col not in cols:
                cur.execute(f'ALTER TABLE {table} ADD COLUMN {col} INTEGER DEFAULT 0')
    con.commit()
