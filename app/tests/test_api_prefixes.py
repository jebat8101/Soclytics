"""Assert platform templates use platform-prefixed API paths."""
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
THREADS_TEMPLATES = [
    os.path.join(TEMPLATES_DIR, 'threads', 'index.html'),
    os.path.join(TEMPLATES_DIR, 'threads', 'analysis.html'),
]
TELEGRAM_TEMPLATES = [
    os.path.join(TEMPLATES_DIR, 'telegram', 'index.html'),
    os.path.join(TEMPLATES_DIR, 'telegram', 'analysis.html'),
]

# Bare fetch to unprefixed /api/ — must never appear in platform templates
BARE_FETCH_RE = re.compile(r"""fetch\s*\(\s*['`']/api/""")


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


def test_threads_templates_use_platform_api_prefix():
    for path in THREADS_TEMPLATES:
        src = _read(path)
        assert os.path.isfile(path), f'missing template: {path}'
        assert '/threads/api/' in src, f'{path} missing /threads/api/ paths'
        assert not BARE_FETCH_RE.search(src), (
            f'{path} contains bare fetch(\'/api/ — use /threads/api/ instead'
        )


def test_telegram_templates_use_platform_api_prefix():
    for path in TELEGRAM_TEMPLATES:
        src = _read(path)
        assert os.path.isfile(path), f'missing template: {path}'
        assert '/telegram/api/' in src, f'{path} missing /telegram/api/ paths'
        assert not BARE_FETCH_RE.search(src), (
            f'{path} contains bare fetch(\'/api/ — use /telegram/api/ instead'
        )
