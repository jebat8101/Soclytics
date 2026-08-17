import sqlite3
from core.counts import parse_compact_int, as_int, ensure_engagement_columns


def test_parse_compact_int():
    assert parse_compact_int('12') == 12
    assert parse_compact_int('1.2', 'K') == 1200
    assert parse_compact_int('.') is None
    assert as_int(None) == 0
    assert as_int('3') == 3


def test_ensure_engagement_columns(tmp_path):
    con = sqlite3.connect(str(tmp_path / 't.db'))
    con.execute('CREATE TABLE text_posts (id INTEGER PRIMARY KEY, post_url TEXT)')
    con.execute('CREATE TABLE photo_posts (id INTEGER PRIMARY KEY)')
    ensure_engagement_columns(con)
    for table in ('text_posts', 'photo_posts'):
        cols = {r[1] for r in con.execute(f'PRAGMA table_info({table})')}
        assert {'like_count', 'reply_count', 'repost_count'} <= cols
    ensure_engagement_columns(con, tables=('no_such_table',))
    con.close()
