"""Threads SQLite schema + fixture import.

Threads posts live in shared post tables for dashboard compatibility and use
dedicated engagement tables for replies, likes, and reposts.
"""
import json
import os
import sqlite3

from platforms.threads.constants import DB_FILE

ABOUT_JSON = 'threads_about.json'
POSTS_JSON = 'threads_posts.json'


SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_url   TEXT UNIQUE NOT NULL,
    owner_name    TEXT,
    is_locked     INTEGER DEFAULT 0,
    scraped_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS profile_fields (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id    INTEGER NOT NULL,
    section       TEXT,
    field_type    TEXT,
    label         TEXT,
    value         TEXT,
    sub_label     TEXT,
    FOREIGN KEY (profile_id) REFERENCES profiles(id)
);

CREATE TABLE IF NOT EXISTS photo_posts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id    INTEGER NOT NULL,
    photo_url     TEXT UNIQUE NOT NULL,
    date_text     TEXT,
    image_src     TEXT,
    caption       TEXT,
    scraped_at    TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (profile_id) REFERENCES profiles(id)
);

CREATE TABLE IF NOT EXISTS reel_posts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id    INTEGER NOT NULL,
    reel_url      TEXT UNIQUE NOT NULL,
    scraped_at    TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (profile_id) REFERENCES profiles(id)
);

CREATE TABLE IF NOT EXISTS text_posts (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id        INTEGER NOT NULL,
    post_url          TEXT UNIQUE NOT NULL,
    date_text         TEXT,
    screenshot_path   TEXT,
    body              TEXT,
    media_type        TEXT,
    image_src         TEXT,
    scraped_at        TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (profile_id) REFERENCES profiles(id)
);

CREATE TABLE IF NOT EXISTS commentors (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_url   TEXT UNIQUE NOT NULL,
    name          TEXT
);

CREATE TABLE IF NOT EXISTS photo_comments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    photo_post_id INTEGER NOT NULL,
    commentor_id  INTEGER NOT NULL,
    comment_text  TEXT,
    FOREIGN KEY (photo_post_id) REFERENCES photo_posts(id),
    FOREIGN KEY (commentor_id)  REFERENCES commentors(id),
    UNIQUE(photo_post_id, commentor_id, comment_text)
);

CREATE TABLE IF NOT EXISTS reel_comments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    reel_post_id  INTEGER NOT NULL,
    commentor_id  INTEGER NOT NULL,
    comment_text  TEXT,
    FOREIGN KEY (reel_post_id) REFERENCES reel_posts(id),
    FOREIGN KEY (commentor_id) REFERENCES commentors(id),
    UNIQUE(reel_post_id, commentor_id, comment_text)
);

CREATE TABLE IF NOT EXISTS text_comments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    text_post_id  INTEGER NOT NULL,
    commentor_id  INTEGER NOT NULL,
    comment_text  TEXT,
    FOREIGN KEY (text_post_id) REFERENCES text_posts(id),
    FOREIGN KEY (commentor_id) REFERENCES commentors(id),
    UNIQUE(text_post_id, commentor_id, comment_text)
);

CREATE TABLE IF NOT EXISTS thread_replies (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id       INTEGER NOT NULL,
    commentor_id  INTEGER NOT NULL,
    comment_text  TEXT,
    FOREIGN KEY (post_id) REFERENCES text_posts(id),
    FOREIGN KEY (commentor_id) REFERENCES commentors(id),
    UNIQUE(post_id, commentor_id, comment_text)
);

CREATE TABLE IF NOT EXISTS thread_likes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id       INTEGER NOT NULL,
    commentor_id  INTEGER NOT NULL,
    FOREIGN KEY (post_id) REFERENCES text_posts(id),
    FOREIGN KEY (commentor_id) REFERENCES commentors(id),
    UNIQUE(post_id, commentor_id)
);

CREATE TABLE IF NOT EXISTS thread_reposts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id       INTEGER NOT NULL,
    commentor_id  INTEGER NOT NULL,
    FOREIGN KEY (post_id) REFERENCES text_posts(id),
    FOREIGN KEY (commentor_id) REFERENCES commentors(id),
    UNIQUE(post_id, commentor_id)
);

CREATE TABLE IF NOT EXISTS commentor_frequency (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id        INTEGER NOT NULL,
    commentor_id      INTEGER NOT NULL,
    photo_count       INTEGER DEFAULT 0,
    reel_count        INTEGER DEFAULT 0,
    text_count        INTEGER DEFAULT 0,
    like_count        INTEGER DEFAULT 0,
    repost_count      INTEGER DEFAULT 0,
    reply_count       INTEGER DEFAULT 0,
    total_count       INTEGER DEFAULT 0,
    calculated_at     TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (profile_id)   REFERENCES profiles(id),
    FOREIGN KEY (commentor_id) REFERENCES commentors(id),
    UNIQUE(profile_id, commentor_id)
);

CREATE TABLE IF NOT EXISTS top7_profiles (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id    INTEGER NOT NULL,
    commentor_id  INTEGER NOT NULL,
    profile_url   TEXT NOT NULL,
    name          TEXT,
    comment_count INTEGER DEFAULT 0,
    rank          INTEGER DEFAULT 0,
    scraped_at    TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (profile_id)   REFERENCES profiles(id),
    FOREIGN KEY (commentor_id) REFERENCES commentors(id),
    UNIQUE(profile_id, commentor_id)
);

CREATE TABLE IF NOT EXISTS top7_profile_fields (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    top7_profile_id   INTEGER NOT NULL,
    section           TEXT,
    field_type        TEXT,
    label             TEXT,
    value             TEXT,
    sub_label         TEXT,
    FOREIGN KEY (top7_profile_id) REFERENCES top7_profiles(id)
);

CREATE TABLE IF NOT EXISTS face_clusters (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    person_label          TEXT NOT NULL,
    representative_face   TEXT,
    appearance_count      INTEGER DEFAULT 0,
    post_ids              TEXT,
    created_at            TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS detected_faces (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    photo_post_id     INTEGER,
    text_post_id      INTEGER,
    face_index        INTEGER DEFAULT 0,
    face_image_path   TEXT,
    encoding          BLOB,
    person_id         INTEGER,
    detected_at       TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (photo_post_id) REFERENCES photo_posts(id),
    FOREIGN KEY (text_post_id)  REFERENCES text_posts(id),
    FOREIGN KEY (person_id)     REFERENCES face_clusters(id)
);
"""


def init_db(db_file=DB_FILE):
    con = sqlite3.connect(db_file)
    con.executescript(SCHEMA)
    con.commit()
    con.close()
    print(f'  DB initialized: {db_file}')


def get_or_create_profile(cur, profile_url, owner_name=None, is_locked=0):
    cur.execute('SELECT id FROM profiles WHERE profile_url = ?', (profile_url,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(
        'INSERT INTO profiles (profile_url, owner_name, is_locked) VALUES (?, ?, ?)',
        (profile_url, owner_name, is_locked),
    )
    return cur.lastrowid


def get_or_create_commentor(cur, profile_url, name):
    cur.execute('SELECT id FROM commentors WHERE profile_url = ?', (profile_url,))
    row = cur.fetchone()
    if row:
        if name:
            cur.execute(
                'UPDATE commentors SET name = ? WHERE id = ? AND name IS NULL',
                (name, row[0]),
            )
        return row[0]
    cur.execute(
        'INSERT INTO commentors (profile_url, name) VALUES (?, ?)',
        (profile_url, name),
    )
    return cur.lastrowid


def import_about(about_json=ABOUT_JSON, db_file=DB_FILE, expected_profile_url=None):
    if not os.path.exists(about_json):
        print(f'  {about_json} not found - skipping')
        return None

    with open(about_json, encoding='utf-8') as f:
        data = json.load(f)

    profile_url = data.get('profile_url', '')
    owner_name = data.get('owner_name')
    is_locked = 1 if data.get('is_locked') else 0
    sections = data.get('sections', {})

    if not profile_url:
        print('  No profile_url in about.json - skipping')
        return None

    if expected_profile_url:
        from core.urls import normalize_threads_target

        try:
            actual = normalize_threads_target(profile_url)
        except ValueError:
            actual = profile_url.strip().rstrip('/').lower()
        try:
            expected = normalize_threads_target(expected_profile_url)
        except ValueError:
            expected = expected_profile_url.strip().rstrip('/').lower()
        if actual != expected:
            msg = (
                f'about.json profile_url mismatch: got {profile_url!r}, '
                f'expected {expected_profile_url!r} - refusing'
            )
            print(f'  {msg}')
            raise ValueError(msg)

    con = sqlite3.connect(db_file)
    cur = con.cursor()
    cur.executescript(SCHEMA)
    profile_id = get_or_create_profile(cur, profile_url, owner_name, is_locked)
    cur.execute('DELETE FROM profile_fields WHERE profile_id = ?', (profile_id,))

    field_count = 0
    for section, fields in sections.items():
        for field in fields:
            cur.execute(
                """
                INSERT INTO profile_fields
                    (profile_id, section, field_type, label, value, sub_label)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    profile_id,
                    section,
                    field.get('field_type'),
                    field.get('label'),
                    field.get('value'),
                    field.get('sub_label'),
                ),
            )
            field_count += 1

    con.commit()
    con.close()
    print(f'  About imported - {field_count} fields for: {owner_name or profile_url}')
    return profile_id


def import_posts(posts_json=POSTS_JSON, db_file=DB_FILE, profile_id=None):
    if not os.path.exists(posts_json):
        print(f'  {posts_json} not found - skipping')
        return 0

    with open(posts_json, encoding='utf-8') as f:
        items = json.load(f)

    con = sqlite3.connect(db_file)
    cur = con.cursor()
    cur.executescript(SCHEMA)
    if not profile_id:
        print('  No profile_id - skipping posts')
        con.close()
        return 0

    post_count = 0
    reply_count = 0
    like_count = 0
    repost_count = 0

    for item in items:
        post_url = item.get('post_url') or item.get('url', '')
        if not post_url:
            continue

        caption = item.get('caption') or item.get('text') or item.get('body')
        image_src = item.get('image_src')
        media_type = item.get('media_type') or ('image' if image_src else 'text')
        date_text = item.get('date')

        cur.execute(
            """
            INSERT OR IGNORE INTO photo_posts
                (profile_id, photo_url, date_text, image_src, caption)
            VALUES (?, ?, ?, ?, ?)
            """,
            (profile_id, post_url, date_text, image_src, caption),
        )
        cur.execute(
            """
            INSERT OR IGNORE INTO text_posts
                (profile_id, post_url, date_text, body, media_type, image_src)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (profile_id, post_url, date_text, caption, media_type, image_src),
        )
        cur.execute(
            """
            INSERT OR IGNORE INTO reel_posts
                (profile_id, reel_url)
            VALUES (?, ?)
            """,
            (profile_id, post_url),
        )
        post_count += 1

        cur.execute('SELECT id FROM photo_posts WHERE photo_url = ?', (post_url,))
        photo_post_id = cur.fetchone()[0]
        cur.execute('SELECT id FROM text_posts WHERE post_url = ?', (post_url,))
        text_post_id = cur.fetchone()[0]
        cur.execute('SELECT id FROM reel_posts WHERE reel_url = ?', (post_url,))
        reel_post_id = cur.fetchone()[0]

        for reply in item.get('replies', []):
            c_url = reply.get('profile_url', '')
            c_name = reply.get('name', '')
            c_text = reply.get('comment_text', '')
            if not c_url:
                continue
            cid = get_or_create_commentor(cur, c_url, c_name)
            cur.execute(
                """
                INSERT OR IGNORE INTO thread_replies
                    (post_id, commentor_id, comment_text)
                VALUES (?, ?, ?)
                """,
                (text_post_id, cid, c_text),
            )
            cur.execute(
                """
                INSERT OR IGNORE INTO text_comments
                    (text_post_id, commentor_id, comment_text)
                VALUES (?, ?, ?)
                """,
                (text_post_id, cid, c_text),
            )
            reply_count += 1

        for like in item.get('likes', []):
            c_url = like.get('profile_url', '')
            c_name = like.get('name', '')
            if not c_url:
                continue
            cid = get_or_create_commentor(cur, c_url, c_name)
            cur.execute(
                """
                INSERT OR IGNORE INTO thread_likes
                    (post_id, commentor_id)
                VALUES (?, ?)
                """,
                (text_post_id, cid),
            )
            cur.execute(
                """
                INSERT OR IGNORE INTO photo_comments
                    (photo_post_id, commentor_id, comment_text)
                VALUES (?, ?, ?)
                """,
                (photo_post_id, cid, '[like]'),
            )
            like_count += 1

        for repost in item.get('reposts', []):
            c_url = repost.get('profile_url', '')
            c_name = repost.get('name', '')
            if not c_url:
                continue
            cid = get_or_create_commentor(cur, c_url, c_name)
            cur.execute(
                """
                INSERT OR IGNORE INTO thread_reposts
                    (post_id, commentor_id)
                VALUES (?, ?)
                """,
                (text_post_id, cid),
            )
            cur.execute(
                """
                INSERT OR IGNORE INTO reel_comments
                    (reel_post_id, commentor_id, comment_text)
                VALUES (?, ?, ?)
                """,
                (reel_post_id, cid, '[repost]'),
            )
            repost_count += 1

    con.commit()
    con.close()
    print(
        f'  Posts imported - {post_count} posts, {reply_count} replies, '
        f'{like_count} likes, {repost_count} reposts'
    )
    return post_count


def compute_frequency(db_file=DB_FILE, profile_id=None):
    if not profile_id:
        print('  No profile_id - skipping frequency computation')
        return 0

    con = sqlite3.connect(db_file)
    cur = con.cursor()
    cur.execute('DELETE FROM commentor_frequency WHERE profile_id = ?', (profile_id,))

    cur.execute(
        """
        SELECT tl.commentor_id, COUNT(*)
        FROM thread_likes tl
        JOIN text_posts tp ON tp.id = tl.post_id
        WHERE tp.profile_id = ?
        GROUP BY tl.commentor_id
        """,
        (profile_id,),
    )
    like_counts = {row[0]: row[1] for row in cur.fetchall()}

    cur.execute(
        """
        SELECT tr.commentor_id, COUNT(*)
        FROM thread_reposts tr
        JOIN text_posts tp ON tp.id = tr.post_id
        WHERE tp.profile_id = ?
        GROUP BY tr.commentor_id
        """,
        (profile_id,),
    )
    repost_counts = {row[0]: row[1] for row in cur.fetchall()}

    cur.execute(
        """
        SELECT tr.commentor_id, COUNT(*)
        FROM thread_replies tr
        JOIN text_posts tp ON tp.id = tr.post_id
        WHERE tp.profile_id = ?
        GROUP BY tr.commentor_id
        """,
        (profile_id,),
    )
    reply_counts = {row[0]: row[1] for row in cur.fetchall()}

    all_ids = set(like_counts) | set(repost_counts) | set(reply_counts)
    for cid in all_ids:
        like_total = like_counts.get(cid, 0)
        repost_total = repost_counts.get(cid, 0)
        reply_total = reply_counts.get(cid, 0)
        total = like_total + repost_total + reply_total
        cur.execute(
            """
            INSERT OR REPLACE INTO commentor_frequency
                (profile_id, commentor_id, photo_count, reel_count, text_count,
                 like_count, repost_count, reply_count, total_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                profile_id,
                cid,
                like_total,
                repost_total,
                reply_total,
                like_total,
                repost_total,
                reply_total,
                total,
            ),
        )

    con.commit()
    con.close()
    print(f'  Frequency computed - {len(all_ids)} commentors')
    return len(all_ids)


def extract_top7(db_file=DB_FILE, profile_id=None):
    if not profile_id:
        return []

    con = sqlite3.connect(db_file)
    cur = con.cursor()
    cur.execute('DELETE FROM top7_profiles WHERE profile_id = ?', (profile_id,))
    cur.execute(
        """
        SELECT cf.commentor_id, co.name, co.profile_url, cf.total_count
        FROM commentor_frequency cf
        JOIN commentors co ON co.id = cf.commentor_id
        WHERE cf.profile_id = ?
        ORDER BY cf.total_count DESC
        LIMIT 7
        """,
        (profile_id,),
    )

    top7 = []
    for rank, row in enumerate(cur.fetchall(), 1):
        cid, name, profile_url, count = row
        cur.execute(
            """
            INSERT OR REPLACE INTO top7_profiles
                (profile_id, commentor_id, profile_url, name, comment_count, rank)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (profile_id, cid, profile_url, name, count, rank),
        )
        top7.append(
            {
                'commentor_id': cid,
                'name': name,
                'profile_url': profile_url,
                'count': count,
                'rank': rank,
            }
        )

    con.commit()
    con.close()
    print(f'  Top 7 extracted - {len(top7)} interactors')
    return top7


def import_all(
    about_json=ABOUT_JSON,
    posts_json=POSTS_JSON,
    db_file=DB_FILE,
    expected_profile_url=None,
):
    print('\n' + '═' * 65)
    print('Soclytics - Threads DB Importer')
    print('═' * 65)

    init_db(db_file)
    profile_id = import_about(
        about_json,
        db_file,
        expected_profile_url=expected_profile_url,
    )

    if not profile_id:
        if expected_profile_url:
            print('  About import refused or missing - cannot import for expected profile')
            return None
        con = sqlite3.connect(db_file)
        cur = con.cursor()
        cur.execute('SELECT id FROM profiles ORDER BY id DESC LIMIT 1')
        row = cur.fetchone()
        con.close()
        if row:
            profile_id = row[0]
            print(f'  Using existing profile_id: {profile_id}')
        else:
            print('  No profile found - cannot import')
            return None

    import_posts(posts_json, db_file, profile_id)
    compute_frequency(db_file, profile_id)
    extract_top7(db_file, profile_id)
    return profile_id


if __name__ == '__main__':
    import_all()
