import pytest
from core.urls import (
    normalize_instagram_target,
    normalize_reddit_target,
    normalize_threads_target,
    normalize_telegram_target,
    extract_telegram_username,
)

@pytest.mark.parametrize('raw,expected', [
    ('natgeo', 'https://www.instagram.com/natgeo/'),
    ('@natgeo', 'https://www.instagram.com/natgeo/'),
    ('https://www.instagram.com/natgeo', 'https://www.instagram.com/natgeo/'),
    ('https://instagram.com/natgeo/', 'https://www.instagram.com/natgeo/'),
])
def test_ig_ok(raw, expected):
    assert normalize_instagram_target(raw) == expected

@pytest.mark.parametrize('raw', [
    'https://www.instagram.com/p/ABC/',
    'https://www.instagram.com/explore/tags/x/',
    '',
])
def test_ig_reject(raw):
    with pytest.raises(ValueError):
        normalize_instagram_target(raw)

@pytest.mark.parametrize('raw,expected', [
    ('spez', 'https://www.reddit.com/user/spez/'),
    ('u/spez', 'https://www.reddit.com/user/spez/'),
    ('https://www.reddit.com/user/spez', 'https://www.reddit.com/user/spez/'),
    ('https://old.reddit.com/user/spez/', 'https://www.reddit.com/user/spez/'),
])
def test_reddit_ok(raw, expected):
    assert normalize_reddit_target(raw) == expected

@pytest.mark.parametrize('raw', [
    'https://www.reddit.com/r/python/',
    'https://www.reddit.com/search/?q=x',
    '',
])
def test_reddit_reject(raw):
    with pytest.raises(ValueError):
        normalize_reddit_target(raw)

@pytest.mark.parametrize('raw,expected', [
    ('natgeo', 'https://www.threads.com/@natgeo/'),
    ('@natgeo', 'https://www.threads.com/@natgeo/'),
    ('https://www.threads.com/@natgeo', 'https://www.threads.com/@natgeo/'),
    ('https://www.threads.com/@natgeo/', 'https://www.threads.com/@natgeo/'),
])
def test_threads_ok(raw, expected):
    assert normalize_threads_target(raw) == expected

@pytest.mark.parametrize('raw', [
    'https://www.threads.com/@natgeo/post/ABC',
    'https://www.threads.com/search',
    '',
])
def test_threads_reject(raw):
    with pytest.raises(ValueError):
        normalize_threads_target(raw)

@pytest.mark.parametrize('raw,expected', [
    ('telegram', 'https://t.me/telegram'),
    ('@durov', 'https://t.me/durov'),
    ('https://t.me/telegram', 'https://t.me/telegram'),
    ('https://t.me/s/telegram', 'https://t.me/telegram'),
    ('t.me/durov', 'https://t.me/durov'),
])
def test_telegram_ok(raw, expected):
    assert normalize_telegram_target(raw) == expected
    assert extract_telegram_username(raw) is not None

@pytest.mark.parametrize('raw', [
    'https://t.me/+AbCdEfGh',
    'https://t.me/joinchat/XXXX',
    '',
])
def test_telegram_reject(raw):
    with pytest.raises(ValueError):
        normalize_telegram_target(raw)
