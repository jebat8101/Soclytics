import os

from platforms.x.posts_sb import (
    _parse_compact_int,
    collect_status_urls_from_html,
    parse_tweet_from_html,
    pinned_status_urls_from_html,
    pinned_tweet_ids_from_html,
)

FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')


def test_collect_status_urls_filters_handle_and_analytics():
    html = '''
    <a href="/example/status/111">one</a>
    <a href="https://x.com/example/status/222">two</a>
    <a href="/example/status/111/analytics">skip</a>
    <a href="/other/status/999">other</a>
    <a href="/example/status/333/photo/1">photo</a>
    '''
    urls = collect_status_urls_from_html(html, 'example', max_posts=10)
    assert urls == [
        'https://x.com/example/status/111',
        'https://x.com/example/status/222',
    ]


def test_collect_status_urls_skips_pinned_article():
    html = '''
    <article data-testid="tweet">
      <div data-testid="socialContext">Pinned</div>
      <a href="/example/status/111">pinned</a>
    </article>
    <article data-testid="tweet">
      <a href="/example/status/222">normal</a>
    </article>
    '''
    assert pinned_status_urls_from_html(html, 'example') == {
        'https://x.com/example/status/111',
    }
    assert collect_status_urls_from_html(html, 'example', max_posts=10) == [
        'https://x.com/example/status/222',
    ]


def test_collect_status_urls_skips_json_pinned_ids():
    html = '''
    <script>{"legacy":{"pinned_tweet_ids_str":["1899617447998812224"]}}</script>
    <a href="/example/status/1899617447998812224">pinned icon only</a>
    <a href="/example/status/222">normal</a>
    '''
    assert pinned_tweet_ids_from_html(html) == {'1899617447998812224'}
    assert collect_status_urls_from_html(html, 'example', max_posts=10) == [
        'https://x.com/example/status/222',
    ]


def test_parse_compact_int_ignores_lone_dot():
    assert _parse_compact_int('.') is None
    assert _parse_compact_int('1.2', 'K') == 1200
    assert parse_tweet_from_html('... . Views ... 12 Likes', 'https://x.com/a/status/1')['like_count'] == 12


def test_parse_tweet_from_html_reads_counts():
    html_path = os.path.join(FIXTURES, 'x_status_snippet.html')
    with open(html_path, encoding='utf-8') as f:
        html = f.read()
    parsed = parse_tweet_from_html(html, 'https://x.com/example/status/333')
    assert parsed['caption'] == 'hello from x'
    assert parsed['date'] == '2026-08-03'
    assert parsed['like_count'] == 12
    assert parsed['reply_count'] == 3
    assert parsed['repost_count'] == 2
    assert parsed['view_count'] == 1200
