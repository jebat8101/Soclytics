import sqlite3
from collections import defaultdict
from datetime import datetime

from core.counts import ensure_engagement_columns

_DAY_NAMES = (
    'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday',
)


def _table_names(cur):
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    return {r[0] for r in cur.fetchall()}


def _date_column(cur, table):
    cur.execute(f'PRAGMA table_info({table})')
    cols = {row[1] for row in cur.fetchall()}
    if 'date_text' in cols:
        return 'date_text'
    if 'scraped_at' in cols:
        return 'scraped_at'
    return "''"


def _fetch_rows(cur, tables, profile_id):
    rows = []
    for table in tables:
        date_col = _date_column(cur, table)
        cur.execute(
            f'''
            SELECT {date_col},
                   COALESCE(like_count, 0),
                   COALESCE(reply_count, 0),
                   COALESCE(repost_count, 0)
            FROM {table}
            WHERE profile_id = ?
            ''',
            (profile_id,),
        )
        for date_text, like, comment, repost in cur.fetchall():
            rows.append((date_text or '', int(like), int(comment), int(repost)))
    return rows


def get_activity_metrics(db_file: str, profile_id: int) -> dict:
    empty = {
        'total_like': 0,
        'total_comment': 0,
        'total_repost': 0,
        'by_date': [],
        'by_weekday': [{'day': d, 'like': 0, 'comment': 0, 'repost': 0} for d in _DAY_NAMES],
        'by_hour': [{'hour': h, 'like': 0, 'comment': 0, 'repost': 0} for h in range(24)],
        'has_hour_data': False,
    }
    if not profile_id:
        return empty
    con = sqlite3.connect(db_file)
    present = _table_names(con.cursor())
    tables = tuple(t for t in ('photo_posts', 'reel_posts', 'text_posts') if t in present)
    if tables:
        ensure_engagement_columns(con, tables=tables)
    cur = con.cursor()
    rows = _fetch_rows(cur, tables, profile_id)
    con.close()

    total_like = total_comment = total_repost = 0
    by_date = defaultdict(lambda: {'like': 0, 'comment': 0, 'repost': 0})
    by_wd = {d: {'like': 0, 'comment': 0, 'repost': 0} for d in _DAY_NAMES}
    by_hour = {h: {'like': 0, 'comment': 0, 'repost': 0} for h in range(24)}
    has_hour = False

    for date_text, like, comment, repost in rows:
        total_like += like
        total_comment += comment
        total_repost += repost
        key = date_text or '—'
        by_date[key]['like'] += like
        by_date[key]['comment'] += comment
        by_date[key]['repost'] += repost
        iso = None
        hour = None
        if date_text and len(date_text) >= 10 and date_text[4] == '-' and date_text[7] == '-':
            try:
                iso = datetime.strptime(date_text[:10], '%Y-%m-%d')
            except ValueError:
                iso = None
        if date_text and ('T' in date_text or (len(date_text) >= 13 and date_text[10] == ' ')):
            chunk = date_text.replace('T', ' ')
            try:
                hour = int(chunk[11:13])
                if 0 <= hour <= 23:
                    has_hour = True
                else:
                    hour = None
            except ValueError:
                hour = None
        if iso is not None:
            dname = _DAY_NAMES[iso.weekday()]
            by_wd[dname]['like'] += like
            by_wd[dname]['comment'] += comment
            by_wd[dname]['repost'] += repost
        if hour is not None:
            by_hour[hour]['like'] += like
            by_hour[hour]['comment'] += comment
            by_hour[hour]['repost'] += repost

    return {
        'total_like': total_like,
        'total_comment': total_comment,
        'total_repost': total_repost,
        'by_date': [
            {'date': d, **v} for d, v in sorted(by_date.items(), key=lambda x: x[0])
        ],
        'by_weekday': [{'day': d, **by_wd[d]} for d in _DAY_NAMES],
        'by_hour': [{'hour': h, **by_hour[h]} for h in range(24)],
        'has_hour_data': has_hour,
    }
