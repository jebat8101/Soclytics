"""Smoke tests for PDF / JSON report export."""
import json
import os

import pytest

from platforms.facebook.db import init_db


@pytest.fixture()
def tmp_fb_db(tmp_path):
    db = str(tmp_path / 'test_fb.db')
    init_db(db)
    import sqlite3
    con = sqlite3.connect(db)
    cur = con.cursor()
    cur.execute(
        "INSERT INTO profiles (profile_url, owner_name, is_locked, scraped_at) "
        "VALUES (?, ?, 0, datetime('now'))",
        ('https://www.facebook.com/example', 'Example User'),
    )
    pid = cur.lastrowid
    con.commit()
    con.close()
    return db, pid


def test_gather_and_json(tmp_fb_db):
    from core.report import gather_report_data, generate_json_report

    db, pid = tmp_fb_db
    data = gather_report_data(pid, db, platform='facebook')
    assert data['profile']['id'] == pid
    assert 'interactors' in data
    assert data['meta']['platform'] == 'facebook'

    out = generate_json_report(pid, db, platform='facebook')
    assert out.endswith('.json')
    assert os.path.isfile(out)
    with open(out, encoding='utf-8') as f:
        loaded = json.load(f)
    assert loaded['profile']['owner_name'] == 'Example User'


def test_generate_pdf(tmp_fb_db):
    pytest.importorskip('reportlab')
    pytest.importorskip('matplotlib')
    from core.report import generate_report

    db, pid = tmp_fb_db
    out = generate_report(pid, db, platform='facebook')
    assert out.endswith('.pdf')
    assert os.path.isfile(out)
    assert os.path.getsize(out) > 1000


def test_report_routes_registered():
    from app import create_app
    client = create_app().test_client()
    r = client.get('/facebook/reports/json/999999')
    assert r.status_code == 404
    body = r.get_json()
    assert body and body.get('ok') is False
