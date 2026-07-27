import os
import sqlite3

FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')


def test_bob_engagement_counts_after_import(tmp_path):
    from platforms.threads.db import import_all

    db_file = str(tmp_path / 'socmint_threads.db')
    about = os.path.join(FIXTURES, 'threads_about.json')
    posts = os.path.join(FIXTURES, 'threads_posts.json')

    profile_id = import_all(about, posts, db_file)
    assert profile_id is not None

    con = sqlite3.connect(db_file)
    cur = con.cursor()
    cur.execute(
        """
        SELECT cf.like_count, cf.repost_count, cf.reply_count, cf.total_count
        FROM commentor_frequency cf
        JOIN commentors c ON c.id = cf.commentor_id
        WHERE c.name = 'bob' AND cf.profile_id = ?
        """,
        (profile_id,),
    )
    row = cur.fetchone()
    con.close()

    assert row is not None
    like_count, repost_count, reply_count, total_count = row
    assert like_count == 1
    assert repost_count == 1
    assert reply_count == 1
    assert total_count == 3
