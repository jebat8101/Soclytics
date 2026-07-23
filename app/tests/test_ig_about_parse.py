import os

FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')
PROFILE_URL = 'https://www.instagram.com/example/'


def test_parse_profile_from_html_extracts_username_and_bio():
    from platforms.instagram.about_sb import parse_profile_from_html

    html_path = os.path.join(FIXTURES, 'ig_profile_snippet.html')
    with open(html_path, encoding='utf-8') as f:
        html = f.read()

    result = parse_profile_from_html(html, PROFILE_URL)

    assert result['profile_url'] == PROFILE_URL
    assert result['username'] == 'example'
    assert result['owner_name'] == 'Example User'
    assert result['bio'] == 'hello'
    assert result['website'] == 'https://example.com'
    assert result['followers'] == 10
    assert result['following'] == 5
    assert result['post_count'] == 3
    assert result['is_locked'] is False

    profile_fields = result['sections']['profile']
    by_type = {f['field_type']: f for f in profile_fields}
    assert by_type['bio']['value'] == 'hello'
    assert by_type['website']['value'] == 'https://example.com'
    assert by_type['followers']['value'] == '10'
    assert by_type['following']['value'] == '5'
    assert by_type['post_count']['value'] == '3'
