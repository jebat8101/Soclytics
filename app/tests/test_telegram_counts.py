# app/tests/test_telegram_counts.py
import json, sqlite3
from platforms.telegram.db import import_all, init_db

def test_telegram_import_stores_like_and_repost(tmp_path):
    db = str(tmp_path / 'socmint_tg.db')
    about = tmp_path / 'tg_about.json'
    posts = tmp_path / 'tg_posts.json'
    about.write_text(json.dumps({
        'profile_url': 'https://t.me/example', 'owner_name': 'Ex',
        'is_locked': False, 'sections': {},
    }), encoding='utf-8')
    posts.write_text(json.dumps([{
        'post_url': 'https://t.me/example/1',
        'date': '2026-08-03',
        'screenshot_path': None,
        'comments': [],
        'like_count': 7,
        'reply_count': 0,
        'repost_count': 2,
    }]), encoding='utf-8')
    photos = tmp_path / 'tg_photos.json'
    reels = tmp_path / 'tg_reels.json'
    photos.write_text('[]', encoding='utf-8')
    reels.write_text('[]', encoding='utf-8')
    init_db(db)
    pid = import_all(
        about_json=str(about),
        photos_json=str(photos),
        reels_json=str(reels),
        posts_json=str(posts),
        db_file=db,
    )
    row = sqlite3.connect(db).execute(
        'SELECT like_count, reply_count, repost_count FROM text_posts WHERE profile_id=?',
        (pid,),
    ).fetchone()
    assert row == (7, 0, 2)
