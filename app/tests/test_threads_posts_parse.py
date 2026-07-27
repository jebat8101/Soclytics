import os

FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')
POST_URL = 'https://www.threads.com/@example/post/AaBbCcDd'


def test_parse_post_from_html_extracts_caption_replies_and_media():
    from platforms.threads.posts_sb import parse_post_from_html

    html_path = os.path.join(FIXTURES, 'threads_post_snippet.html')
    with open(html_path, encoding='utf-8') as f:
        html = f.read()

    result = parse_post_from_html(html, POST_URL)

    assert result['post_url'] == POST_URL
    assert result['caption'] == 'hello world'
    assert result['date'] == '2024-07-01'
    assert result['media_type'] == 'image'
    assert result['image_src'] == 'https://cdn.example/img.jpg'
    assert len(result['replies']) == 2
    names = {r['name'] for r in result['replies']}
    assert names == {'alice', 'bob'}
    assert any(r['comment_text'] == 'nice post' for r in result['replies'])
