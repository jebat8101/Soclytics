"""Telegram DB import smoke test."""
import os
import sqlite3

from platforms.telegram.db import init_db, import_all, compute_frequency


FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')


def test_telegram_import_all(tmp_path):
    db = str(tmp_path / 'tg.db')
    init_db(db)
    import_all(
        about_json=os.path.join(FIXTURES, 'telegram_about.json'),
        photos_json=os.path.join(FIXTURES, 'telegram_photos.json'),
        reels_json=os.path.join(FIXTURES, 'telegram_reels.json'),
        posts_json=os.path.join(FIXTURES, 'telegram_posts.json'),
        db_file=db,
    )
    con = sqlite3.connect(db)
    cur = con.cursor()
    cur.execute('SELECT owner_name FROM profiles')
    assert cur.fetchone()[0] == 'Example Channel'
    cur.execute('SELECT COUNT(*) FROM photo_posts')
    assert cur.fetchone()[0] == 1
    cur.execute('SELECT COUNT(*) FROM reel_posts')
    assert cur.fetchone()[0] == 1
    cur.execute('SELECT COUNT(*) FROM text_posts')
    assert cur.fetchone()[0] == 1
    cur.execute('SELECT COUNT(*) FROM commentors')
    assert cur.fetchone()[0] >= 3
    cur.execute('SELECT id FROM profiles')
    pid = cur.fetchone()[0]
    con.close()
    compute_frequency(db, pid)
    con = sqlite3.connect(db)
    cur = con.cursor()
    cur.execute('SELECT COUNT(*) FROM commentor_frequency WHERE profile_id = ?', (pid,))
    assert cur.fetchone()[0] >= 1
    con.close()
