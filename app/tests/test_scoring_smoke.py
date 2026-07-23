import sqlite3
from core.scoring import get_all_interactors

SCHEMA_MIN = """
CREATE TABLE profiles (id INTEGER PRIMARY KEY, profile_url TEXT, owner_name TEXT);
CREATE TABLE commentors (id INTEGER PRIMARY KEY, profile_url TEXT UNIQUE, name TEXT);
CREATE TABLE commentor_frequency (
  id INTEGER PRIMARY KEY, profile_id INT, commentor_id INT,
  photo_count INT, reel_count INT, text_count INT, total_count INT
);
"""

def test_get_all_interactors(tmp_path):
    db = str(tmp_path / 't.db')
    con = sqlite3.connect(db)
    con.executescript(SCHEMA_MIN)
    con.execute("INSERT INTO profiles VALUES (1,'https://x','X')")
    con.execute("INSERT INTO commentors VALUES (1,'https://y','Y')")
    con.execute("INSERT INTO commentor_frequency VALUES (1,1,1,2,0,1,3)")
    con.commit(); con.close()
    rows = get_all_interactors(db, 1)
    assert rows[0]['name'] == 'Y'
    assert rows[0]['total_count'] == 3
