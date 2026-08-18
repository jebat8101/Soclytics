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
