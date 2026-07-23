import importlib.util
import os


def _load_app():
    path = os.path.join(os.path.dirname(__file__), '..', 'app.py')
    spec = importlib.util.spec_from_file_location('birdy_app_reddit', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.app


def test_reddit_home_ok():
    client = _load_app().test_client()
    r = client.get('/reddit/')
    assert r.status_code == 200


def test_start_pipeline_rejects_subreddit_url():
    client = _load_app().test_client()
    r = client.post(
        '/reddit/api/start-pipeline',
        json={'profile_url': 'https://www.reddit.com/r/python/', 'depth': 'light'},
    )
    assert r.status_code == 400
