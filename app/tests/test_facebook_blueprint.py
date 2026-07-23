import importlib.util, os

def _load_app():
    path = os.path.join(os.path.dirname(__file__), '..', 'app.py')
    spec = importlib.util.spec_from_file_location('birdy_app', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.app

def test_root_redirects_to_facebook():
    client = _load_app().test_client()
    r = client.get('/', follow_redirects=False)
    assert r.status_code in (301, 302)
    assert '/facebook' in r.headers.get('Location', '')

def test_facebook_home_ok():
    client = _load_app().test_client()
    r = client.get('/facebook/')
    assert r.status_code == 200
