"""Reddit SQLite schema + fixture import.

Submissions map to text_posts (title/subreddit/body); comments → text_comments.
Frequency increments text_count only. No face step in pipeline.
"""
import sqlite3
import json
import os

from platforms.reddit.constants import DB_FILE

ABOUT_JSON = "reddit_about.json"
SUBMISSIONS_JSON = "reddit_submissions.json"


SCHEMA = """
-- Target profile
CREATE TABLE IF NOT EXISTS profiles (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_url   TEXT UNIQUE NOT NULL,
    owner_name    TEXT,
    is_locked     INTEGER DEFAULT 0,
    scraped_at    TEXT DEFAULT (datetime('now'))
);

-- Profile about fields
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

-- Stub photo/reel tables for scoring schema parity
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

-- Reddit submissions (extended text_posts)
CREATE TABLE IF NOT EXISTS text_posts (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id        INTEGER NOT NULL,
    post_url          TEXT UNIQUE NOT NULL,
    date_text         TEXT,
    screenshot_path   TEXT,
    title             TEXT,
    subreddit         TEXT,
    body              TEXT,
    scraped_at        TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (profile_id) REFERENCES profiles(id)
);

-- Commentors / interactors
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
    UNIQUE(photo_post_id, commentor_id)
);

CREATE TABLE IF NOT EXISTS reel_comments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    reel_post_id  INTEGER NOT NULL,
    commentor_id  INTEGER NOT NULL,
    comment_text  TEXT,
    FOREIGN KEY (reel_post_id) REFERENCES reel_posts(id),
    FOREIGN KEY (commentor_id) REFERENCES commentors(id),
    UNIQUE(reel_post_id, commentor_id)
);

CREATE TABLE IF NOT EXISTS text_comments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    text_post_id  INTEGER NOT NULL,
    commentor_id  INTEGER NOT NULL,
    comment_text  TEXT,
    FOREIGN KEY (text_post_id) REFERENCES text_posts(id),
    FOREIGN KEY (commentor_id) REFERENCES commentors(id),
    UNIQUE(text_post_id, commentor_id)
);

CREATE TABLE IF NOT EXISTS commentor_frequency (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id        INTEGER NOT NULL,
    commentor_id      INTEGER NOT NULL,
    photo_count       INTEGER DEFAULT 0,
    reel_count        INTEGER DEFAULT 0,
    text_count        INTEGER DEFAULT 0,
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

-- Face stubs (unused by Reddit pipeline)
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


def _ensure_text_post_columns(cur):
    """Add title/subreddit/body to text_posts if missing (legacy DBs)."""
    cur.execute("PRAGMA table_info(text_posts)")
    columns = {row[1] for row in cur.fetchall()}
    for col in ('title', 'subreddit', 'body'):
        if col not in columns:
            cur.execute(f"ALTER TABLE text_posts ADD COLUMN {col} TEXT")


def init_db(db_file=DB_FILE):
    """Initialize DB schema unconditionally."""
    con = sqlite3.connect(db_file)
    cur = con.cursor()
    cur.executescript(SCHEMA)
    _ensure_text_post_columns(cur)
    con.commit()
    con.close()
    print(f"  DB initialized: {db_file}")


def get_or_create_profile(cur, profile_url, owner_name=None, is_locked=0):
    cur.execute("SELECT id FROM profiles WHERE profile_url = ?", (profile_url,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(
        "INSERT INTO profiles (profile_url, owner_name, is_locked) VALUES (?, ?, ?)",
        (profile_url, owner_name, is_locked)
    )
    return cur.lastrowid


def get_or_create_commentor(cur, profile_url, name):
    cur.execute("SELECT id FROM commentors WHERE profile_url = ?", (profile_url,))
    row = cur.fetchone()
    if row:
        if name:
            cur.execute(
                "UPDATE commentors SET name = ? WHERE id = ? AND name IS NULL",
                (name, row[0])
            )
        return row[0]
    cur.execute(
        "INSERT INTO commentors (profile_url, name) VALUES (?, ?)",
        (profile_url, name)
    )
    return cur.lastrowid


def import_about(about_json=ABOUT_JSON, db_file=DB_FILE):
    if not os.path.exists(about_json):
        print(f"  {about_json} not found — skipping")
        return None

    with open(about_json, encoding="utf-8") as f:
        data = json.load(f)

    profile_url = data.get("profile_url", "")
    owner_name = data.get("owner_name")
    is_locked = 1 if data.get("is_locked") else 0
    sections = data.get("sections", {})

    if not profile_url:
        print("  No profile_url in about.json — skipping")
        return None

    con = sqlite3.connect(db_file)
    cur = con.cursor()
    cur.executescript(SCHEMA)
    _ensure_text_post_columns(cur)

    profile_id = get_or_create_profile(cur, profile_url, owner_name, is_locked)

    cur.execute("DELETE FROM profile_fields WHERE profile_id = ?", (profile_id,))

    field_count = 0
    for section, fields in sections.items():
        for field in fields:
            cur.execute("""
                INSERT INTO profile_fields
                    (profile_id, section, field_type, label, value, sub_label)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                profile_id,
                section,
                field.get("field_type"),
                field.get("label"),
                field.get("value"),
                field.get("sub_label")
            ))
            field_count += 1

    con.commit()
    con.close()
    print(f"  About imported — {field_count} fields for: {owner_name or profile_url}")
    return profile_id


def import_submissions(submissions_json=SUBMISSIONS_JSON, db_file=DB_FILE, profile_id=None):
    """Import Reddit submissions into text_posts with title/subreddit/body."""
    if not os.path.exists(submissions_json):
        print(f"  {submissions_json} not found — skipping")
        return 0

    with open(submissions_json, encoding="utf-8") as f:
        items = json.load(f)

    con = sqlite3.connect(db_file)
    cur = con.cursor()
    cur.executescript(SCHEMA)
    _ensure_text_post_columns(cur)

    if not profile_id:
        print("  No profile_id — skipping submissions")
        con.close()
        return 0

    post_count = 0
    comment_count = 0

    for item in items:
        post_url = item.get("post_url") or item.get("url", "")
        if not post_url:
            continue

        try:
            cur.execute("""
                INSERT OR IGNORE INTO text_posts
                    (profile_id, post_url, date_text, title, subreddit, body)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                profile_id, post_url,
                item.get("date"),
                item.get("title"),
                item.get("subreddit"),
                item.get("body")
            ))
            cur.execute("""
                UPDATE text_posts
                SET date_text = COALESCE(?, date_text),
                    title = COALESCE(?, title),
                    subreddit = COALESCE(?, subreddit),
                    body = COALESCE(?, body)
                WHERE post_url = ?
            """, (
                item.get("date"),
                item.get("title"),
                item.get("subreddit"),
                item.get("body"),
                post_url,
            ))
            post_count += 1
        except Exception as e:
            print(f"  Submission insert error: {e}")
            continue

        cur.execute("SELECT id FROM text_posts WHERE post_url = ?", (post_url,))
        row = cur.fetchone()
        if not row:
            continue
        post_id = row[0]

        for c in item.get("comments", []):
            c_url = c.get("profile_url", "")
            c_name = c.get("name", "")
            c_text = c.get("comment_text", "")
            if not c_url:
                continue
            cid = get_or_create_commentor(cur, c_url, c_name)
            try:
                cur.execute("""
                    INSERT OR IGNORE INTO text_comments
                        (text_post_id, commentor_id, comment_text)
                    VALUES (?, ?, ?)
                """, (post_id, cid, c_text))
                comment_count += 1
            except Exception:
                pass

    con.commit()
    con.close()
    print(f"  Submissions imported — {post_count} posts, {comment_count} comments")
    return post_count


def compute_frequency(db_file=DB_FILE, profile_id=None):
    """Compute interaction frequency — Reddit only increments text_count."""
    if not profile_id:
        print("  No profile_id — skipping frequency computation")
        return

    con = sqlite3.connect(db_file)
    cur = con.cursor()

    cur.execute(
        "DELETE FROM commentor_frequency WHERE profile_id = ?",
        (profile_id,)
    )

    cur.execute("""
        SELECT tc.commentor_id, COUNT(*) as cnt
        FROM text_comments tc
        JOIN text_posts tp ON tp.id = tc.text_post_id
        WHERE tp.profile_id = ?
        GROUP BY tc.commentor_id
    """, (profile_id,))
    text_counts = {row[0]: row[1] for row in cur.fetchall()}

    for cid, tc in text_counts.items():
        cur.execute("""
            INSERT OR REPLACE INTO commentor_frequency
                (profile_id, commentor_id, photo_count, reel_count,
                 text_count, total_count)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (profile_id, cid, 0, 0, tc, tc))

    con.commit()
    con.close()

    total_commentors = len(text_counts)
    print(f"  Frequency computed — {total_commentors} commentors")
    return total_commentors


def extract_top7(db_file=DB_FILE, profile_id=None):
    """Extract top 7 most frequent interactors into top7_profiles table."""
    if not profile_id:
        return []

    con = sqlite3.connect(db_file)
    cur = con.cursor()

    cur.execute("DELETE FROM top7_profiles WHERE profile_id = ?", (profile_id,))

    cur.execute("""
        SELECT cf.commentor_id, co.name, co.profile_url, cf.total_count
        FROM commentor_frequency cf
        JOIN commentors co ON co.id = cf.commentor_id
        WHERE cf.profile_id = ?
        ORDER BY cf.total_count DESC
        LIMIT 7
    """, (profile_id,))

    top7 = []
    for rank, row in enumerate(cur.fetchall(), 1):
        cid, name, profile_url, count = row
        cur.execute("""
            INSERT OR REPLACE INTO top7_profiles
                (profile_id, commentor_id, profile_url, name, comment_count, rank)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (profile_id, cid, profile_url, name, count, rank))
        top7.append({
            'commentor_id': cid,
            'name': name,
            'profile_url': profile_url,
            'count': count,
            'rank': rank
        })

    con.commit()
    con.close()
    print(f"  Top 7 extracted — {len(top7)} interactors")
    return top7


def import_all(
    about_json=ABOUT_JSON,
    submissions_json=SUBMISSIONS_JSON,
    db_file=DB_FILE
):
    print("\n" + "═" * 65)
    print("BIRDY-EDWARDS LITE — Reddit DB Importer")
    print("═" * 65)

    init_db(db_file)

    profile_id = import_about(about_json, db_file)

    if not profile_id:
        con = sqlite3.connect(db_file)
        cur = con.cursor()
        cur.execute("SELECT id FROM profiles ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        con.close()
        if row:
            profile_id = row[0]
            print(f"  Using existing profile_id: {profile_id}")
        else:
            print("  No profile found — cannot import")
            return

    import_submissions(submissions_json, db_file, profile_id)

    compute_frequency(db_file, profile_id)
    extract_top7(db_file, profile_id)

    con = sqlite3.connect(db_file)
    cur = con.cursor()
    print(f"\n{'═' * 65}")
    print("SUMMARY")
    print("═" * 65)
    for table in ['profiles', 'photo_posts', 'reel_posts', 'text_posts',
                  'commentors', 'photo_comments', 'reel_comments',
                  'text_comments', 'commentor_frequency', 'top7_profiles']:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            print(f"  {table:25s} → {cur.fetchone()[0]} rows")
        except Exception:
            pass
    con.close()
    print(f"\nImport complete → {db_file}")
    return profile_id


if __name__ == "__main__":
    import_all()
