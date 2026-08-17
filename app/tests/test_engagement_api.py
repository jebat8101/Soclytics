import importlib.util
import os


def _load_app():
    path = os.path.join(os.path.dirname(__file__), '..', 'app.py')
    spec = importlib.util.spec_from_file_location('birdy_app', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.app


def test_facebook_activity_metrics_ok():
    r = _load_app().test_client().get('/facebook/api/activity-metrics/1')
    assert r.status_code == 200
    body = r.get_json()
    assert 'ok' in body


def test_x_activity_metrics_ok():
    r = _load_app().test_client().get('/x/api/activity-metrics/1')
    assert r.status_code == 200
