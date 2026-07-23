from core.browser import (
    cookies_have_domain, filter_cookies_for_domain,
    save_cookies_pickle, load_cookies_pickle,
)

def test_domain_helpers():
    cookies = [
        {'name': 'c_user', 'value': '1', 'domain': '.facebook.com'},
        {'name': 'sessionid', 'value': 'x', 'domain': '.instagram.com'},
    ]
    assert cookies_have_domain(cookies, 'instagram.com') is True
    assert cookies_have_domain(cookies, 'reddit.com') is False
    ig = filter_cookies_for_domain(cookies, 'instagram.com')
    assert len(ig) == 1 and ig[0]['name'] == 'sessionid'

def test_pickle_roundtrip(tmp_path):
    path = str(tmp_path / 'c.pkl')
    save_cookies_pickle(path, [{'name': 'a', 'value': 'b', 'domain': '.x.com'}])
    assert load_cookies_pickle(path)[0]['name'] == 'a'
