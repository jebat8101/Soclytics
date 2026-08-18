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

    con = sqlite3.connect(db_file)
    cur = con.cursor()
    cur.execute(
        """
        SELECT like_count, reply_count, repost_count FROM text_posts
        WHERE profile_id = ?
        """,
        (profile_id,),
    )
    counts = cur.fetchone()
    con.close()

    assert counts == (12, 5, 3)


def test_missing_count_keys_store_zero(tmp_path):
    import json
    from platforms.threads.db import import_all

    db_file = str(tmp_path / 'socmint_threads.db')
    about = os.path.join(FIXTURES, 'threads_about.json')
    posts_src = os.path.join(FIXTURES, 'threads_posts.json')
    with open(posts_src, encoding='utf-8') as f:
        items = json.load(f)
    for item in items:
        item.pop('like_count', None)
        item.pop('reply_count', None)
        item.pop('repost_count', None)
    posts = str(tmp_path / 'threads_posts_no_counts.json')
    with open(posts, 'w', encoding='utf-8') as f:
        json.dump(items, f)

    profile_id = import_all(about, posts, db_file)
    assert profile_id is not None

    con = sqlite3.connect(db_file)
    row = con.execute(
        'SELECT like_count, reply_count, repost_count FROM text_posts WHERE profile_id=?',
        (profile_id,),
    ).fetchone()
    con.close()

    assert row == (0, 0, 0)


def test_import_stores_source_tab(tmp_path):
    import json
    from platforms.threads.db import import_all

    db_file = str(tmp_path / 'socmint_threads.db')
    about = os.path.join(FIXTURES, 'threads_about.json')
    posts_src = os.path.join(FIXTURES, 'threads_posts.json')
    with open(posts_src, encoding='utf-8') as f:
        items = json.load(f)
    items[0]['source_tab'] = 'replies'
    posts = str(tmp_path / 'threads_posts_replies_tab.json')
    with open(posts, 'w', encoding='utf-8') as f:
        json.dump(items, f)

    profile_id = import_all(about, posts, db_file)
    con = sqlite3.connect(db_file)
    row = con.execute(
        'SELECT source_tab FROM text_posts WHERE profile_id=?',
        (profile_id,),
    ).fetchone()
    con.close()
    assert row == ('replies',)
