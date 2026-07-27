import pickle


def cookies_have_domain(cookies: list[dict], domain_substr: str) -> bool:
    return any(domain_substr in c.get('domain', '') for c in cookies)


def cookies_have_any_domain(cookies: list[dict], domain_substrs: list[str]) -> bool:
    return any(cookies_have_domain(cookies, d) for d in domain_substrs)


def filter_cookies_for_domain(cookies: list[dict], domain_substr: str) -> list[dict]:
    return [c for c in cookies if domain_substr in c.get('domain', '')]


def filter_cookies_for_any_domain(cookies: list[dict], domain_substrs: list[str]) -> list[dict]:
    seen = set()
    out = []
    for d in domain_substrs:
        for c in filter_cookies_for_domain(cookies, d):
            key = (c.get('name'), c.get('domain'), c.get('path', '/'))
            if key in seen:
                continue
            seen.add(key)
            out.append(c)
    return out


def save_cookies_pickle(path: str, cookies: list[dict]) -> None:
    with open(path, 'wb') as f:
        pickle.dump(cookies, f)


def load_cookies_pickle(path: str) -> list[dict]:
    with open(path, 'rb') as f:
        return pickle.load(f)
