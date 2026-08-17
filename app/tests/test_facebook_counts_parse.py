import os
from platforms.facebook.counts_parse import parse_facebook_engagement

FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')


def test_parse_facebook_engagement_footer():
    html = open(os.path.join(FIXTURES, 'fb_engagement_snippet.html'), encoding='utf-8').read()
    got = parse_facebook_engagement(html)
    assert got == {'like_count': 1200, 'reply_count': 45, 'repost_count': 12}


def test_parse_facebook_engagement_missing():
    assert parse_facebook_engagement('hello') == {
        'like_count': 0, 'reply_count': 0, 'repost_count': 0,
    }
