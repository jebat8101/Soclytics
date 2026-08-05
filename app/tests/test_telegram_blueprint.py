"""Telegram blueprint route smoke tests."""
from app import create_app


def test_telegram_home_ok():
    client = create_app().test_client()
    r = client.get('/telegram/')
    assert r.status_code == 200
    assert b'Telegram' in r.data


def test_telegram_session_endpoints():
    client = create_app().test_client()
    r = client.get('/telegram/api/check-session')
    assert r.status_code == 200
    data = r.get_json()
    assert data['ok'] is True
    assert data['ready'] is True
    assert 'message' in data

    r2 = client.get('/telegram/api/verify-session')
    assert r2.status_code == 200
    assert r2.get_json()['ok'] is True


def test_telegram_rejects_invite_link():
    client = create_app().test_client()
    r = client.post(
        '/telegram/api/start-pipeline',
        json={'profile_url': 'https://t.me/+privatehash', 'depth': 'light'},
    )
    assert r.status_code == 400
    assert r.get_json()['ok'] is False


def test_telegram_start_pipeline_accepts_public(monkeypatch):
    """Pipeline starts without cookies; collector is stubbed to avoid network."""
    import platforms.telegram.blueprint as bp

    def fake_collect(url, max_posts=5, max_photos=5, max_reels=5):
        return {
            'mode': 'stub',
            'counts': {'photos': 0, 'reels': 0, 'posts': 0, 'comments': 0},
        }

    monkeypatch.setattr(bp, 'collect', fake_collect)
    # Also stub import/scoring to keep the background thread quiet
    monkeypatch.setattr(bp, 'import_all', lambda **kwargs: None)
    monkeypatch.setattr(bp, 'compute_frequency', lambda *a, **k: None)
    monkeypatch.setattr(bp, 'extract_top7', lambda *a, **k: None)
    monkeypatch.setattr(bp, 'get_profile_id', lambda db: {'id': 1})
    monkeypatch.setattr(bp, 'FACE_AVAILABLE', False)

    client = create_app().test_client()
    # Ensure not already running from a prior test
    bp.pipeline_state['running'] = False
    r = client.post(
        '/telegram/api/start-pipeline',
        json={'profile_url': 'https://t.me/telegram', 'depth': 'light'},
    )
    assert r.status_code == 200
    assert r.get_json()['ok'] is True


def test_telegram_cookies_rejected():
    client = create_app().test_client()
    r = client.post('/telegram/api/import-cookies', json={'cookies': []})
    assert r.status_code == 400
    assert 'MTProto' in r.get_json()['error']
