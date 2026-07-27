import os

FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')
PROFILE_URL = 'https://www.threads.com/@example/'


def test_parse_profile_from_html_extracts_username_and_bio():
    from platforms.threads.about_sb import parse_profile_from_html

    html_path = os.path.join(FIXTURES, 'threads_profile_snippet.html')
    with open(html_path, encoding='utf-8') as f:
        html = f.read()

    result = parse_profile_from_html(html, PROFILE_URL)

    assert result['profile_url'] == PROFILE_URL
    assert result['username'] == 'example'
    assert result['owner_name'] == 'Example User'
    assert result['bio'] == 'hello threads'
    assert result['website'] == 'https://example.com'
    assert result['followers'] == 10
    assert result['following'] == 5
    assert result['is_locked'] is False

    profile_fields = result['sections']['profile']
    by_type = {f['field_type']: f for f in profile_fields}
    assert by_type['bio']['value'] == 'hello threads'
    assert by_type['website']['value'] == 'https://example.com'
    assert by_type['followers']['value'] == '10'
