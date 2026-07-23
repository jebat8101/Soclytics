import core.face as face


def test_load_local_image_anchors_to_app_dir(tmp_path, monkeypatch):
    """Relative screenshot paths resolve under app/, not core/."""
    shot_dir = tmp_path / 'post_screenshots'
    shot_dir.mkdir()
    target = shot_dir / 'shot.jpg'
    target.write_bytes(b'fake-jpeg-bytes')

    monkeypatch.setattr(face, 'APP_DIR', str(tmp_path))
    data = face._load_local_image('post_screenshots/shot.jpg')
    assert data == b'fake-jpeg-bytes'


def test_scoring_db_file_default():
    from core.scoring import DB_FILE
    assert DB_FILE == 'socmint_fb.db'
