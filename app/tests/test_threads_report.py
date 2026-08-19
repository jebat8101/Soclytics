import json
import os
import sqlite3

import pytest

FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')


def _import_threads_db(tmp_path, source_tab='threads'):
    from platforms.threads.db import import_all

    db = str(tmp_path / 'socmint_threads.db')
    about = os.path.join(FIXTURES, 'threads_about.json')
    posts_src = os.path.join(FIXTURES, 'threads_posts.json')
    with open(posts_src, encoding='utf-8') as f:
        items = json.load(f)
    items[0]['source_tab'] = source_tab
    posts = str(tmp_path / 'threads_posts_tab.json')
    with open(posts, 'w', encoding='utf-8') as f:
        json.dump(items, f)
    pid = import_all(about, posts, db)
    assert pid
    return db, pid


def test_threads_json_feed_matches_dashboard_tabs(tmp_path):
    from core.report import generate_json_report

    db, pid = _import_threads_db(tmp_path, source_tab='replies')
    out = generate_json_report(pid, db, platform='threads')
    with open(out, encoding='utf-8') as f:
        dumped = json.load(f)
    feed = dumped['feed']
    assert set(feed.keys()) == {'threads', 'replies', 'media', 'reposts'}
    assert len(feed['replies']) == 1
    item = feed['replies'][0]
    assert item['source_tab'] == 'replies'
    assert item['reply_count'] == 5
    assert item['like_count'] == 12
    assert 'view_count' not in item


def test_threads_json_includes_dashboard_activity_timeline(tmp_path):
    from core.engagement_metrics import get_activity_metrics
    from core.report import gather_report_data, generate_json_report

    db, pid = _import_threads_db(tmp_path)
    expected = get_activity_metrics(db, pid)
    data = gather_report_data(pid, db, platform='threads')
    activity = data['activity']
    assert activity is not None
    assert activity['total_like'] == expected['total_like'] == 12
    assert activity['total_comment'] == expected['total_comment'] == 5
    assert activity['total_repost'] == expected['total_repost'] == 3
    by_date = {r['date']: r for r in activity['by_date']}
    assert by_date['2026-07-01']['like'] == 12
    assert by_date['2026-07-01']['comment'] == 5
    assert by_date['2026-07-01']['repost'] == 3

    out = generate_json_report(pid, db, platform='threads')
    with open(out, encoding='utf-8') as f:
        dumped = json.load(f)
    dumped_act = dumped['activity']
    assert dumped_act['total_like'] == 12
    assert dumped_act['total_comment'] == 5
    assert dumped_act['total_repost'] == 3
    dumped_days = {r['date']: r for r in dumped_act['by_date']}
    assert dumped_days['2026-07-01']['like'] == 12


def test_threads_pdf_has_tab_sections_and_metrics(tmp_path):
    pytest.importorskip('reportlab')
    from core.report import build_threads_posts, gather_report_data, make_styles

    db, pid = _import_threads_db(tmp_path, source_tab='threads')
    data = gather_report_data(pid, db, platform='threads')
    story = build_threads_posts(data['posts'], make_styles())

    def collect_text(items, acc=None):
        acc = [] if acc is None else acc
        for it in items or []:
            text = getattr(it, 'text', None)
            if text:
                acc.append(str(text))
            inner = getattr(it, '_content', None) or getattr(it, 'content', None)
            if inner:
                collect_text(inner, acc)
            cells = getattr(it, '_cellvalues', None)
            if cells:
                for row in cells:
                    collect_text(row if isinstance(row, (list, tuple)) else [row], acc)
        return acc

    blob = '\n'.join(collect_text(story))
    assert 'Threads ·' in blob
    assert 'Replies ·' in blob
    assert 'Media ·' in blob
    assert 'Reposts ·' in blob
    assert 'Comment' in blob and 'Like' in blob
    assert 'View  ' not in blob


def test_threads_pdf_has_activity_timeline(tmp_path):
    pytest.importorskip('reportlab')
    pytest.importorskip('matplotlib')
    from core.report import generate_report

    db, pid = _import_threads_db(tmp_path)
    out = generate_report(pid, db, platform='threads', out_path=str(tmp_path / 'threads.pdf'))
    assert os.path.isfile(out)
    try:
        from pypdf import PdfReader
    except ImportError:
        pytest.skip('pypdf required to assert PDF text')
    text = '\n'.join((p.extract_text() or '') for p in PdfReader(out).pages)
    assert 'ACTIVITY TIMELINE' in text
    assert 'Like' in text
    assert 'Comment' in text
    assert 'Repost' in text
    assert '12' in text and '5' in text and '3' in text
    assert 'Active Days' not in text
    assert 'Like / Comment / Repost by date' not in text
    assert 'No hour timestamps' not in text


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


def _sample_activity():
    days = ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday')
    return {
        'total_like': 12,
        'total_comment': 5,
        'total_repost': 3,
        'by_date': [{'date': '2026-07-01', 'like': 12, 'comment': 5, 'repost': 3}],
        'by_weekday': [
            {'day': d, 'like': 12 if d == 'Wednesday' else 0, 'comment': 5 if d == 'Wednesday' else 0, 'repost': 3 if d == 'Wednesday' else 0}
            for d in days
        ],
        'by_hour': [{'hour': h, 'like': 0, 'comment': 0, 'repost': 0} for h in range(24)],
        'has_hour_data': False,
    }


def test_threads_activity_story_matches_dashboard_card():
    pytest.importorskip('reportlab')
    from core.report import build_engagement_activity_timeline, make_styles

    story = build_engagement_activity_timeline(_sample_activity(), make_styles())
    blob = '\n'.join(_flowable_text(story))
    assert 'ACTIVITY TIMELINE' in blob
    assert 'LIKE' in blob and 'COMMENT' in blob and 'REPOST' in blob
    assert '12' in blob and '5' in blob and '3' in blob
    assert 'Active Days' not in blob
    assert 'Like / Comment / Repost by date' not in blob


def test_engagement_activity_charts_use_dashboard_dark_theme():
    pytest.importorskip('matplotlib')
    import matplotlib.image as mpimg
    from core.report import chart_engagement_activity_day, chart_engagement_activity_weekday_hour

    activity = _sample_activity()
    day_buf = chart_engagement_activity_day(activity)
    split_buf = chart_engagement_activity_weekday_hour(activity)
    assert day_buf is not None and split_buf is not None
    for buf in (day_buf, split_buf):
        buf.seek(0)
        arr = mpimg.imread(buf)
        corner = arr[4, 4, :3]
        assert float(corner.mean()) < 0.25, corner


def test_posts_for_threads_tab_media_excludes_reposts(tmp_path):
    from core.report import _posts_for_threads_tab

    rows = [
        {'source_tab': 'threads', 'media_type': 'text', 'post_url': 'https://a/1'},
        {'source_tab': 'replies', 'media_type': 'text', 'post_url': 'https://a/2'},
        {'source_tab': 'reposts', 'media_type': 'image', 'post_url': 'https://a/3'},
        {'source_tab': 'media', 'media_type': 'image', 'post_url': 'https://a/4'},
    ]
    media = _posts_for_threads_tab(rows, 'media')
    urls = [r['post_url'] for r in media]
    assert 'https://a/4' in urls
    assert 'https://a/3' not in urls
