# app/tests/test_ig_counts_parse.py
import os
from platforms.instagram.posts_sb import parse_post_from_html

def test_ig_parse_reads_like_and_comment_counts():
    html = open(os.path.join(os.path.dirname(__file__), 'fixtures/ig_engagement_snippet.html'), encoding='utf-8').read()
    got = parse_post_from_html(html, 'https://www.instagram.com/p/AAA/')
    assert got['like_count'] == 12
    assert got['reply_count'] == 3
    assert got['repost_count'] == 0
