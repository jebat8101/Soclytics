# app/tests/test_reddit_counts.py
import json, os, sqlite3
from platforms.reddit.db import import_all, init_db

def test_reddit_import_maps_score_to_like(tmp_path):
    db = str(tmp_path / 'socmint_reddit.db')
    about = tmp_path / 'reddit_about.json'
    posts = tmp_path / 'reddit_submissions.json'
    about.write_text(json.dumps({
        'profile_url': 'https://www.reddit.com/user/example/',
        'owner_name': 'example', 'is_locked': False, 'sections': {},
    }), encoding='utf-8')
    posts.write_text(json.dumps([{
        'post_url': 'https://www.reddit.com/r/x/comments/abc/t/',
        'date': '2026-08-03', 'title': 't', 'subreddit': 'x', 'body': '',
        'score': 42, 'comments': [{'name': 'a', 'profile_url': 'https://www.reddit.com/user/a/', 'comment_text': 'hi'}],
        'like_count': 42, 'reply_count': 1, 'repost_count': 0,
    }]), encoding='utf-8')
    init_db(db)
    pid = import_all(str(about), str(posts), db)
    row = sqlite3.connect(db).execute(
        'SELECT like_count, reply_count, repost_count FROM text_posts WHERE profile_id=?',
        (pid,),
    ).fetchone()
    assert row == (42, 1, 0)
