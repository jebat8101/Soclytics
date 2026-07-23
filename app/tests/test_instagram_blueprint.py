import importlib.util
import os


def _load_app():
    path = os.path.join(os.path.dirname(__file__), '..', 'app.py')
    spec = importlib.util.spec_from_file_location('birdy_app_ig', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.app


def test_instagram_home_ok():
    client = _load_app().test_client()
    r = client.get('/instagram/')
    assert r.status_code == 200


def test_start_pipeline_rejects_post_url():
    client = _load_app().test_client()
    r = client.post(
        '/instagram/api/start-pipeline',
        json={'profile_url': 'https://www.instagram.com/p/x/', 'depth': 'light'},
    )
    assert r.status_code == 400
