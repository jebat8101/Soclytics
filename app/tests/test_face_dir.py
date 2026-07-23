import sqlite3

import core.face as face


def _minimal_face_db(path):
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE profiles (
            id INTEGER PRIMARY KEY, owner_name TEXT
        );
        CREATE TABLE photo_posts (
            id INTEGER PRIMARY KEY,
            profile_id INTEGER,
            photo_url TEXT,
            image_src TEXT,
            caption TEXT
        );
        CREATE TABLE text_posts (
            id INTEGER PRIMARY KEY,
            profile_id INTEGER,
            post_url TEXT,
            screenshot_path TEXT
        );
    """)
    con.execute("INSERT INTO profiles (id, owner_name) VALUES (1, 'TestUser')")
    con.execute(
        "INSERT INTO photo_posts (id, profile_id, photo_url, image_src, caption) "
        "VALUES (1, 1, '', 'http://example.com/a.jpg', '')"
    )
    con.commit()
    con.close()


def test_run_face_clustering_uses_face_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(face, 'FACE_RECOGNITION_AVAILABLE', True)
    monkeypatch.setattr(face, '_process_image', lambda *a, **k: [])

    db_file = str(tmp_path / 't.db')
    face_dir = str(tmp_path / 'custom_faces')
    _minimal_face_db(db_file)

    face.run_face_clustering(db_file, 1, face_dir=face_dir)

    assert (tmp_path / 'custom_faces' / 'TestUser' / 'raw').is_dir()
    assert (tmp_path / 'custom_faces' / 'TestUser' / 'persons').is_dir()


def test_run_face_clustering_defaults_to_app_face_data(tmp_path, monkeypatch):
    monkeypatch.setattr(face, 'FACE_RECOGNITION_AVAILABLE', True)
    monkeypatch.setattr(face, 'APP_DIR', str(tmp_path))
    monkeypatch.setattr(face, '_process_image', lambda *a, **k: [])

    db_file = str(tmp_path / 't.db')
    _minimal_face_db(db_file)

    face.run_face_clustering(db_file, 1)

    assert (tmp_path / 'face_data' / 'TestUser' / 'raw').is_dir()
