"""X.com SQLite schema + fixture import.

Tweets live in text_posts with numeric engagement columns. Actor tables exist
for scoring/UI compatibility but are not populated (counts-only collection).
"""
import json
import os
import sqlite3

from platforms.x.constants import DB_FILE

ABOUT_JSON = 'x_about.json'
POSTS_JSON = 'x_posts.json'


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
    like_count        INTEGER DEFAULT 0,
    reply_count       INTEGER DEFAULT 0,
    repost_count      INTEGER DEFAULT 0,
    view_count        INTEGER DEFAULT 0,
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
    _ensure_count_columns(con)
    con.commit()
    con.close()
    print(f'  DB initialized: {db_file}')


def _ensure_count_columns(con):
    cur = con.cursor()
    cur.execute('PRAGMA table_info(text_posts)')
    cols = {row[1] for row in cur.fetchall()}
    for col in ('like_count', 'reply_count', 'repost_count', 'view_count'):
        if col not in cols:
            cur.execute(f'ALTER TABLE text_posts ADD COLUMN {col} INTEGER DEFAULT 0')


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
        from core.urls import normalize_x_target

        try:
            actual = normalize_x_target(profile_url)
        except ValueError:
            actual = profile_url.strip().rstrip('/').lower()
        try:
            expected = normalize_x_target(expected_profile_url)
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
    _ensure_count_columns(con)
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


def _as_int(val) -> int:
    if val is None or val == '':
        return 0
    try:
        return int(val)
    except (TypeError, ValueError):
        return 0


def import_posts(posts_json=POSTS_JSON, db_file=DB_FILE, profile_id=None):
    if not os.path.exists(posts_json):
        print(f'  {posts_json} not found - skipping')
        return 0

    with open(posts_json, encoding='utf-8') as f:
        items = json.load(f)

    con = sqlite3.connect(db_file)
    cur = con.cursor()
    cur.executescript(SCHEMA)
    _ensure_count_columns(con)
    if not profile_id:
        print('  No profile_id - skipping posts')
        con.close()
        return 0

    post_count = 0
    for item in items:
        post_url = item.get('post_url') or item.get('url', '')
        if not post_url:
            continue

        caption = item.get('caption') or item.get('text') or item.get('body')
        image_src = item.get('image_src')
        media_type = item.get('media_type') or ('image' if image_src else 'text')
        date_text = item.get('date')
        like_count = _as_int(item.get('like_count'))
        reply_count = _as_int(item.get('reply_count'))
        repost_count = _as_int(item.get('repost_count'))
        view_count = _as_int(item.get('view_count'))

        cur.execute(
            """
            INSERT INTO text_posts
                (profile_id, post_url, date_text, body, media_type, image_src,
                 like_count, reply_count, repost_count, view_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(post_url) DO UPDATE SET
                date_text = excluded.date_text,
                body = excluded.body,
                media_type = excluded.media_type,
                image_src = excluded.image_src,
                like_count = excluded.like_count,
                reply_count = excluded.reply_count,
                repost_count = excluded.repost_count,
                view_count = excluded.view_count
            """,
            (
                profile_id, post_url, date_text, caption, media_type, image_src,
                like_count, reply_count, repost_count, view_count,
            ),
        )
        post_count += 1

    keep_urls = [
        item.get('post_url') or item.get('url', '')
        for item in items
        if item.get('post_url') or item.get('url')
    ]
    if keep_urls:
        placeholders = ','.join('?' * len(keep_urls))
        stale = f'''
            SELECT id FROM text_posts
            WHERE profile_id = ? AND post_url NOT IN ({placeholders})
        '''
        cur.execute(
            f'DELETE FROM detected_faces WHERE text_post_id IN ({stale})',
            (profile_id, *keep_urls),
        )
        cur.execute(
            f'DELETE FROM text_comments WHERE text_post_id IN ({stale})',
            (profile_id, *keep_urls),
        )
        cur.execute(
            f'DELETE FROM text_posts WHERE profile_id = ? AND post_url NOT IN ({placeholders})',
            (profile_id, *keep_urls),
        )
        dropped = cur.rowcount
        if dropped:
            print(f'  Removed {dropped} stale/pinned tweet(s) not in this scrape')

    con.commit()
    con.close()
    print(f'  Posts imported - {post_count} tweets (counts only)')
    return post_count


def compute_frequency(db_file=DB_FILE, profile_id=None):
    """Counts-only: no interactors. Clears frequency rows for the profile."""
    if not profile_id:
        print('  No profile_id - skipping frequency computation')
        return 0
    con = sqlite3.connect(db_file)
    cur = con.cursor()
    cur.execute('DELETE FROM commentor_frequency WHERE profile_id = ?', (profile_id,))
    con.commit()
    con.close()
    print('  Frequency computed - 0 commentors (counts-only X module)')
    return 0


def extract_top7(db_file=DB_FILE, profile_id=None):
    if not profile_id:
        return []
    con = sqlite3.connect(db_file)
    cur = con.cursor()
    cur.execute('DELETE FROM top7_profiles WHERE profile_id = ?', (profile_id,))
    con.commit()
    con.close()
    print('  Top 7 extracted - 0 interactors (counts-only X module)')
    return []


def get_x_engagement(db_file=DB_FILE, profile_id=None):
    """Native X.com totals: posts + reply / repost / like / view."""
    empty = {'posts': 0, 'reply': 0, 'repost': 0, 'like': 0, 'view': 0}
    if not profile_id:
        return empty
    con = sqlite3.connect(db_file)
    cur = con.cursor()
    cur.execute(
        """
        SELECT COUNT(*),
               COALESCE(SUM(reply_count), 0),
               COALESCE(SUM(repost_count), 0),
               COALESCE(SUM(like_count), 0),
               COALESCE(SUM(view_count), 0)
        FROM text_posts
        WHERE profile_id = ?
        """,
        (profile_id,),
    )
    posts, reply, repost, like, view = cur.fetchone()
    con.close()
    return {
        'posts': int(posts or 0),
        'reply': int(reply or 0),
        'repost': int(repost or 0),
        'like': int(like or 0),
        'view': int(view or 0),
    }


def get_x_timeline(db_file=DB_FILE, profile_id=None):
    """Date-wise Reply / Repost / Like / View sums."""
    if not profile_id:
        return []
    con = sqlite3.connect(db_file)
    cur = con.cursor()
    cur.execute(
        """
        SELECT date_text,
               COALESCE(SUM(reply_count), 0),
               COALESCE(SUM(repost_count), 0),
               COALESCE(SUM(like_count), 0),
               COALESCE(SUM(view_count), 0)
        FROM text_posts
        WHERE profile_id = ? AND date_text IS NOT NULL AND TRIM(date_text) != ''
        GROUP BY date_text
        ORDER BY date_text
        """,
        (profile_id,),
    )
    rows = []
    for date_text, replies, reposts, likes, views in cur.fetchall():
        reply = int(replies or 0)
        repost = int(reposts or 0)
        like = int(likes or 0)
        view = int(views or 0)
        rows.append({
            'date': date_text,
            'reply': reply,
            'repost': repost,
            'like': like,
            'view': view,
            'replies': reply,
            'reposts': repost,
            'likes': like,
            'views': view,
            'photo': like,
            'reel': repost,
            'text': reply,
            'total': reply + repost + like,
        })
    con.close()
    return rows


def import_all(
    about_json=ABOUT_JSON,
    posts_json=POSTS_JSON,
    db_file=DB_FILE,
    expected_profile_url=None,
):
    print('\n' + '═' * 65)
    print('Soclytics - X DB Importer')
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
