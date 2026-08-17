import sqlite3
from core.counts import ensure_engagement_columns
from core.engagement_metrics import get_activity_metrics


def _seed(path):
    con = sqlite3.connect(path)
    con.executescript(
        '''
        CREATE TABLE profiles (id INTEGER PRIMARY KEY);
        CREATE TABLE text_posts (
            id INTEGER PRIMARY KEY, profile_id INTEGER, post_url TEXT UNIQUE,
            date_text TEXT
        );
        INSERT INTO profiles (id) VALUES (1);
        '''
    )
    ensure_engagement_columns(con, tables=('text_posts',))
    con.execute(
        '''INSERT INTO text_posts
           (profile_id, post_url, date_text, like_count, reply_count, repost_count)
           VALUES (1, 'u1', '2026-08-03', 10, 2, 1)'''
    )
    con.execute(
        '''INSERT INTO text_posts
           (profile_id, post_url, date_text, like_count, reply_count, repost_count)
           VALUES (1, 'u2', 'not-a-date', 5, 0, 0)'''
    )
    con.commit()
    con.close()


def test_activity_metrics_stacks_like_comment_repost(tmp_path):
    db = str(tmp_path / 'm.db')
    _seed(db)
    data = get_activity_metrics(db, 1)
    assert data['total_like'] == 15
    assert data['total_comment'] == 2
    assert data['total_repost'] == 1
    by_date = {r['date']: r for r in data['by_date']}
    assert by_date['2026-08-03']['like'] == 10
    assert by_date['not-a-date']['like'] == 5
    monday = next(r for r in data['by_weekday'] if r['day'] == 'Monday')
    assert monday['like'] == 10
    assert data['has_hour_data'] is False
