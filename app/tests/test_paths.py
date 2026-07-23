import os
import pytest

from core.paths import safe_under


def test_safe_under_allows_nested_relative(tmp_path):
    base = str(tmp_path)
    (tmp_path / 'face_data' / 'alice').mkdir(parents=True)
    target = tmp_path / 'face_data' / 'alice' / 'crop.jpg'
    target.write_bytes(b'x')

    result = safe_under(base, 'face_data/alice/crop.jpg')
    assert result == os.path.realpath(str(target))


def test_safe_under_rejects_dotdot(tmp_path):
    with pytest.raises(ValueError, match='traversal'):
        safe_under(str(tmp_path), '../etc/passwd')


def test_safe_under_rejects_absolute(tmp_path):
    with pytest.raises(ValueError, match='absolute'):
        safe_under(str(tmp_path), '/etc/passwd')


def test_safe_under_rejects_empty(tmp_path):
    with pytest.raises(ValueError, match='empty'):
        safe_under(str(tmp_path), '')
