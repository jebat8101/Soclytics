"""Path safety helpers for media-serving routes."""
import os


def safe_under(base_dir: str, rel_path: str) -> str:
    """
    Resolve rel_path under base_dir, rejecting absolute paths and '..' traversal.

    Returns the real absolute path. Raises ValueError if the path is unsafe
    or would escape base_dir.
    """
    if rel_path is None or rel_path == '':
        raise ValueError('empty path')
    # Reject absolute paths (POSIX and Windows-style)
    if os.path.isabs(rel_path) or rel_path.startswith(('/', '\\')):
        raise ValueError('absolute path rejected')
    # Reject any '..' segment before join
    normalized = rel_path.replace('\\', '/')
    parts = [p for p in normalized.split('/') if p not in ('', '.')]
    if any(p == '..' for p in parts):
        raise ValueError('path traversal rejected')

    base = os.path.realpath(base_dir)
    candidate = os.path.realpath(os.path.join(base, *parts))
    if os.path.commonpath([base, candidate]) != base:
        raise ValueError('path escapes base directory')
    return candidate
