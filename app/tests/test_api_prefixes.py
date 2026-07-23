"""Assert Instagram/Reddit templates use platform-prefixed API paths."""
import os
import re

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), '..', 'templates')

IG_TEMPLATES = [
    os.path.join(TEMPLATES_DIR, 'instagram', 'index.html'),
    os.path.join(TEMPLATES_DIR, 'instagram', 'analysis.html'),
]
REDDIT_TEMPLATES = [
    os.path.join(TEMPLATES_DIR, 'reddit', 'index.html'),
    os.path.join(TEMPLATES_DIR, 'reddit', 'analysis.html'),
]

# Bare fetch to unprefixed /api/ — must never appear in IG/Reddit templates
BARE_FETCH_RE = re.compile(r"""fetch\s*\(\s*['`]/api/""")


def _read(path: str) -> str:
    with open(path, encoding='utf-8') as f:
        return f.read()


def test_instagram_templates_use_platform_api_prefix():
    for path in IG_TEMPLATES:
        src = _read(path)
        assert os.path.isfile(path), f'missing template: {path}'
        assert '/instagram/api/' in src, f'{path} missing /instagram/api/ paths'
        assert not BARE_FETCH_RE.search(src), (
            f'{path} contains bare fetch(\'/api/ — use /instagram/api/ instead'
        )


def test_reddit_templates_use_platform_api_prefix():
    for path in REDDIT_TEMPLATES:
        src = _read(path)
        assert os.path.isfile(path), f'missing template: {path}'
        assert '/reddit/api/' in src, f'{path} missing /reddit/api/ paths'
        assert not BARE_FETCH_RE.search(src), (
            f'{path} contains bare fetch(\'/api/ — use /reddit/api/ instead'
        )
