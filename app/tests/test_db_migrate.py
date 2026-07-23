import os
from core.db_base import migrate_legacy_fb_db

def test_renames_legacy(tmp_path):
    legacy = tmp_path / 'socmint_lite.db'
    legacy.write_bytes(b'sqlite')
    path = migrate_legacy_fb_db(str(tmp_path))
    assert path.endswith('socmint_fb.db')
    assert os.path.exists(path)
    assert not os.path.exists(legacy)

def test_prefers_new_when_both(tmp_path):
    (tmp_path / 'socmint_lite.db').write_bytes(b'old')
    new = tmp_path / 'socmint_fb.db'
    new.write_bytes(b'new')
    path = migrate_legacy_fb_db(str(tmp_path))
    assert path == str(new)
    assert (tmp_path / 'socmint_lite.db').exists()

def test_returns_new_path_when_missing(tmp_path):
    path = migrate_legacy_fb_db(str(tmp_path))
    assert path.endswith('socmint_fb.db')
    assert not os.path.exists(path)
