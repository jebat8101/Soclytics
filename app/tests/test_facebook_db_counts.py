# app/tests/test_facebook_db_counts.py
import os, sqlite3
from platforms.facebook.db import import_all, init_db

FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')


def test_facebook_import_stores_counts(tmp_path):
    db = str(tmp_path / 'socmint_fb.db')
    init_db(db)
    pid = import_all(
        about_json=os.path.join(FIXTURES, 'fb_about_counts.json'),
        photos_json=os.path.join(FIXTURES, 'missing.json'),
        reels_json=os.path.join(FIXTURES, 'missing.json'),
        posts_json=os.path.join(FIXTURES, 'fb_posts_counts.json'),
        db_file=db,
    )
    assert pid
    con = sqlite3.connect(db)
    row = con.execute(
        'SELECT like_count, reply_count, repost_count FROM text_posts WHERE profile_id=?',
        (pid,),
    ).fetchone()
    con.close()
    assert row == (10, 2, 1)
