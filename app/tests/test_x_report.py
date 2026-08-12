"""X.com report uses native Post / Reply / Repost / Like / View structure."""
import os

import pytest

FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')


@pytest.fixture()
def tmp_x_db(tmp_path):
    from platforms.x.db import import_all

    db = str(tmp_path / 'socmint_x.db')
    pid = import_all(
        os.path.join(FIXTURES, 'x_about.json'),
        os.path.join(FIXTURES, 'x_posts.json'),
        db,
    )
    assert pid is not None
    return db, pid


def test_x_engagement_and_timeline(tmp_x_db):
    from platforms.x.db import get_x_engagement, get_x_timeline

    db, pid = tmp_x_db
    eng = get_x_engagement(db, pid)
    assert eng == {'posts': 2, 'reply': 4, 'repost': 2, 'like': 17, 'view': 490}

    days = get_x_timeline(db, pid)
    assert [d['date'] for d in days] == ['2026-08-01', '2026-08-02']
    assert days[0]['reply'] == 3
    assert days[0]['repost'] == 2
    assert days[0]['like'] == 12
    assert days[0]['view'] == 400


def test_x_json_report_posts_have_counts(tmp_x_db):
    from core.report import gather_report_data, generate_json_report

    db, pid = tmp_x_db
    data = gather_report_data(pid, db, platform='x')
    assert data['meta']['platform'] == 'x'
    assert data['engagement'] == {'posts': 2, 'reply': 4, 'repost': 2, 'like': 17, 'view': 490}
    posts = data['posts']['texts']
    assert len(posts) == 2
    one = next(p for p in posts if 'status/111' in (p.get('url') or ''))
    assert one['caption'] == 'first tweet'
    assert one['reply_count'] == 3
    assert one['repost_count'] == 2
    assert one['like_count'] == 12
    assert one['view_count'] == 400

    out = generate_json_report(pid, db, platform='x')
    assert os.path.isfile(out)
    assert 'report_x_' in os.path.basename(out)
    import json
    with open(out, encoding='utf-8') as f:
        dumped = json.load(f)
    assert dumped['engagement']['view'] == 490
    assert isinstance(dumped['posts'], list)
    assert 'interactors' not in dumped
    one_j = next(p for p in dumped['posts'] if 'status/111' in (p.get('post_url') or ''))
    assert one_j['body'] == 'first tweet'
    assert one_j['reply_count'] == 3
    assert one_j['repost_count'] == 2
    assert one_j['like_count'] == 12
    assert one_j['view_count'] == 400


def test_x_pdf_report(tmp_x_db):
    pytest.importorskip('reportlab')
    pytest.importorskip('matplotlib')
    from core.report import generate_report

    db, pid = tmp_x_db
    out = generate_report(pid, db, platform='x')
    assert out.endswith('.pdf')
    assert os.path.isfile(out)
    assert os.path.getsize(out) > 1000
    try:
        from pypdf import PdfReader
    except ImportError:
        return
    text = '\n'.join((p.extract_text() or '') for p in PdfReader(out).pages)
    for needle in (
        'ENGAGEMENT MIX', 'ENGAGEMENT TIMELINE', 'X POSTS',
        'Reply', 'Repost', 'Like', 'View', 'first tweet',
    ):
        assert needle in text, needle
