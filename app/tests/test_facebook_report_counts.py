# app/tests/test_facebook_report_counts.py
import json
import os

import pytest
from platforms.facebook.db import import_all, init_db
from core.report import gather_report_data

FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')


def _import_counts_db(tmp_path):
    db = str(tmp_path / 'socmint_fb.db')
    init_db(db)
    pid = import_all(
        about_json=os.path.join(FIXTURES, 'fb_about_counts.json'),
        photos_json=os.path.join(FIXTURES, 'missing.json'),
        reels_json=os.path.join(FIXTURES, 'missing.json'),
        posts_json=os.path.join(FIXTURES, 'fb_posts_counts.json'),
        db_file=db,
    )
    assert pid
    return db, pid


def test_facebook_json_has_engagement(tmp_path):
    db, pid = _import_counts_db(tmp_path)
    data = gather_report_data(pid, db, platform='facebook')
    assert data['engagement']['like'] == 10
    assert data['engagement']['comment'] == 2
    assert data['engagement']['repost'] == 1
    assert data['posts']['texts'][0]['like_count'] == 10


def _flowable_text(items, acc=None):
    acc = [] if acc is None else acc
    for it in items or []:
        text = getattr(it, 'text', None)
        if text:
            acc.append(str(text))
        inner = getattr(it, '_content', None) or getattr(it, 'content', None)
        if inner:
            _flowable_text(inner, acc)
        cells = getattr(it, '_cellvalues', None)
        if cells:
            for row in cells:
                _flowable_text(row if isinstance(row, (list, tuple)) else [row], acc)
    return acc


def test_facebook_posts_pdf_matches_dashboard_metrics(tmp_path):
    pytest.importorskip('reportlab')
    from core.report import build_posts, make_styles

    db, pid = _import_counts_db(tmp_path)
    data = gather_report_data(pid, db, platform='facebook')
    story = build_posts(data['posts'], make_styles(), tweet_cards=True)
    blob = '\n'.join(_flowable_text(story))
    assert 'Comment  2' in blob or 'Comment 2' in blob
    assert 'Repost  1' in blob or 'Repost 1' in blob
    assert 'Like  10' in blob or 'Like 10' in blob
    assert 'View' not in blob


def test_facebook_json_report_includes_dashboard_feed(tmp_path):
    from core.report import generate_json_report

    db, pid = _import_counts_db(tmp_path)
    out = generate_json_report(pid, db, platform='facebook')
    with open(out, encoding='utf-8') as f:
        dumped = json.load(f)
    item = dumped['feed']['texts'][0]
    assert item['like_count'] == 10
    assert item['reply_count'] == 2
    assert item['repost_count'] == 1
    assert 'view_count' not in item
    assert dumped['profile']['owner_name']
