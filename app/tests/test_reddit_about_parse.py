import os

FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')
PROFILE_URL = 'https://www.reddit.com/user/example/'


def test_parse_profile_from_html_extracts_karma_and_cake_day():
    from platforms.reddit.about_sb import parse_profile_from_html

    html_path = os.path.join(FIXTURES, 'reddit_profile_snippet.html')
    with open(html_path, encoding='utf-8') as f:
        html = f.read()

    result = parse_profile_from_html(html, PROFILE_URL)

    assert result['profile_url'] == PROFILE_URL
    assert result['owner_name'] == 'example'
    assert result['is_locked'] is False

    by_type = {f['field_type']: f for f in result['sections']['profile']}
    assert by_type['karma']['label'] == 'Post Karma'
    assert by_type['karma']['value'] == '123'
    assert by_type['cake_day']['label'] == 'Cake Day'
    assert by_type['cake_day']['value'] == '2020-01-01'
    assert by_type['comment_karma']['value'] == '45'


def test_parse_submissions_list_from_html():
    from platforms.reddit.submissions_sb import parse_submissions_list_from_html

    html_path = os.path.join(FIXTURES, 'reddit_submissions_snippet.html')
    with open(html_path, encoding='utf-8') as f:
        html = f.read()

    items = parse_submissions_list_from_html(html, max_posts=10)

    assert len(items) == 1
    item = items[0]
    assert item['post_url'] == 'https://www.reddit.com/r/test/comments/abc/title/'
    assert item['title'] == 'Hello'
    assert item['subreddit'] == 'test'
    assert item['date'] == '2026-01-01'
    assert item['body'] == 'world'
    assert item['score'] == 10
    assert item['comments'] == []


def test_parse_comments_from_html():
    from platforms.reddit.submissions_sb import parse_comments_from_html

    html_path = os.path.join(FIXTURES, 'reddit_comments_snippet.html')
    with open(html_path, encoding='utf-8') as f:
        html = f.read()

    comments = parse_comments_from_html(html)

    assert len(comments) == 1
    assert comments[0]['name'] == 'alice'
    assert comments[0]['profile_url'] == 'https://www.reddit.com/user/alice/'
    assert comments[0]['comment_text'] == 'hi'


def test_require_cookies_raises_when_missing(tmp_path, monkeypatch):
    from platforms.reddit import about_sb

    missing = str(tmp_path / 'missing_reddit_cookies.pkl')
    monkeypatch.setattr(about_sb, 'COOKIE_FILE', missing)

    try:
        about_sb._require_cookies()
        assert False, 'expected FileNotFoundError'
    except FileNotFoundError as e:
        assert 'cookie' in str(e).lower()
