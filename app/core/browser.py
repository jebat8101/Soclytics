import pickle


def cookies_have_domain(cookies: list[dict], domain_substr: str) -> bool:
    return any(domain_substr in c.get('domain', '') for c in cookies)


def filter_cookies_for_domain(cookies: list[dict], domain_substr: str) -> list[dict]:
    return [c for c in cookies if domain_substr in c.get('domain', '')]


def save_cookies_pickle(path: str, cookies: list[dict]) -> None:
    with open(path, 'wb') as f:
        pickle.dump(cookies, f)


def load_cookies_pickle(path: str) -> list[dict]:
    with open(path, 'rb') as f:
        return pickle.load(f)
