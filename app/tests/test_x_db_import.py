import os
import sqlite3

FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')


def test_x_import_stores_engagement_counts(tmp_path):
    from platforms.x.db import import_all

    db_file = str(tmp_path / 'socmint_x.db')
    about = os.path.join(FIXTURES, 'x_about.json')
    posts = os.path.join(FIXTURES, 'x_posts.json')

    profile_id = import_all(about, posts, db_file)
    assert profile_id is not None

    con = sqlite3.connect(db_file)
    cur = con.cursor()
    cur.execute(
        """
        SELECT post_url, like_count, reply_count, repost_count, view_count
        FROM text_posts
        WHERE profile_id = ?
        ORDER BY post_url
        """,
        (profile_id,),
    )
    rows = cur.fetchall()
    cur.execute(
        'SELECT COUNT(*) FROM commentor_frequency WHERE profile_id = ?',
        (profile_id,),
    )
    freq = cur.fetchone()[0]
    con.close()

    assert len(rows) == 2
    by_url = {r[0]: r[1:] for r in rows}
    assert by_url['https://x.com/example/status/111'] == (12, 3, 2, 400)
    assert by_url['https://x.com/example/status/222'] == (5, 1, 0, 90)
    assert freq == 0
