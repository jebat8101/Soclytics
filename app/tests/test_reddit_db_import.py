import os
import sqlite3

FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')


def test_alice_total_count_after_import_and_frequency(tmp_path):
    from platforms.reddit.db import import_all, compute_frequency

    db_file = str(tmp_path / 'socmint_reddit.db')
    about = os.path.join(FIXTURES, 'reddit_about.json')
    submissions = os.path.join(FIXTURES, 'reddit_submissions.json')

    import_all(about, submissions, db_file)

    con = sqlite3.connect(db_file)
    cur = con.cursor()
    cur.execute("SELECT id FROM profiles LIMIT 1")
    profile_id = cur.fetchone()[0]
    con.close()

    compute_frequency(db_file, profile_id)

    con = sqlite3.connect(db_file)
    cur = con.cursor()
    cur.execute("""
        SELECT cf.total_count, cf.text_count
        FROM commentor_frequency cf
        JOIN commentors c ON c.id = cf.commentor_id
        WHERE c.name = 'alice' AND cf.profile_id = ?
    """, (profile_id,))
    row = cur.fetchone()
    con.close()

    assert row is not None
    assert row[0] == 1
    assert row[1] == 1
