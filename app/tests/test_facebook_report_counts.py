# app/tests/test_facebook_report_counts.py
import os
from platforms.facebook.db import import_all, init_db
from core.report import gather_report_data

FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')

def test_facebook_json_has_engagement(tmp_path):
    db = str(tmp_path / 'socmint_fb.db')
    init_db(db)
    pid = import_all(
        about_json=os.path.join(FIXTURES, 'fb_about_counts.json'),
        photos_json=os.path.join(FIXTURES, 'missing.json'),
        reels_json=os.path.join(FIXTURES, 'missing.json'),
        posts_json=os.path.join(FIXTURES, 'fb_posts_counts.json'),
        db_file=db,
    )
    data = gather_report_data(pid, db, platform='facebook')
    assert data['engagement']['like'] == 10
    assert data['engagement']['comment'] == 2
    assert data['engagement']['repost'] == 1
    assert data['posts']['texts'][0]['like_count'] == 10
