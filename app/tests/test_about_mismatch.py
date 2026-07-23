import json
import os

import pytest

FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')


def test_ig_import_about_refuses_mismatched_profile_url(tmp_path):
    from platforms.instagram.db import import_about

    about = tmp_path / 'ig_about.json'
    about.write_text(json.dumps({
        'profile_url': 'https://www.instagram.com/attacker/',
        'owner_name': 'Attacker',
        'is_locked': False,
        'sections': {},
    }), encoding='utf-8')
    db_file = str(tmp_path / 'socmint_ig.db')

    with pytest.raises(ValueError, match='mismatch'):
        import_about(
            str(about),
            db_file,
            expected_profile_url='https://www.instagram.com/example/',
        )


def test_ig_import_about_accepts_matching_profile_url(tmp_path):
    from platforms.instagram.db import import_about

    about = os.path.join(FIXTURES, 'ig_about.json')
    db_file = str(tmp_path / 'socmint_ig.db')
    pid = import_about(
        about,
        db_file,
        expected_profile_url='https://www.instagram.com/example/',
    )
    assert pid is not None


def test_reddit_import_about_refuses_mismatched_profile_url(tmp_path):
    from platforms.reddit.db import import_about

    about = tmp_path / 'reddit_about.json'
    about.write_text(json.dumps({
        'profile_url': 'https://www.reddit.com/user/attacker/',
        'owner_name': 'attacker',
        'is_locked': False,
        'sections': {},
    }), encoding='utf-8')
    db_file = str(tmp_path / 'socmint_reddit.db')

    with pytest.raises(ValueError, match='mismatch'):
        import_about(
            str(about),
            db_file,
            expected_profile_url='https://www.reddit.com/user/example/',
        )


def test_reddit_import_about_accepts_matching_profile_url(tmp_path):
    from platforms.reddit.db import import_about

    about = os.path.join(FIXTURES, 'reddit_about.json')
    db_file = str(tmp_path / 'socmint_reddit.db')
    pid = import_about(
        about,
        db_file,
        expected_profile_url='https://www.reddit.com/user/example/',
    )
    assert pid is not None
