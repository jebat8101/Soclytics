import os

FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')
POST_URL = 'https://www.threads.com/@example/post/AaBbCcDd'


def test_profile_tab_url_matches_native_threads_structure():
    from platforms.threads.posts_sb import profile_tab_url

    base = 'https://www.threads.com/@dlmjhfra/'
    assert profile_tab_url(base, 'threads') == 'https://www.threads.com/@dlmjhfra/'
    assert profile_tab_url(base, 'replies') == 'https://www.threads.com/@dlmjhfra/replies/'
    assert profile_tab_url(base, 'media') == 'https://www.threads.com/@dlmjhfra/media/'
    assert profile_tab_url(base, 'reposts') == 'https://www.threads.com/@dlmjhfra/reposts/'


def test_merge_tab_urls_follows_threads_replies_media_reposts():
    from platforms.threads.posts_sb import merge_tab_urls

    profile = 'https://www.threads.com/@dlmjhfra/'
    merged = merge_tab_urls(
        {
            'threads': [
                'https://www.threads.com/@dlmjhfra/post/Own1',
                'https://www.threads.com/@other/post/Skip',
            ],
            'replies': ['https://www.threads.com/@dlmjhfra/post/Reply1'],
            'media': ['https://www.threads.com/@dlmjhfra/post/Own1'],
            'reposts': ['https://www.threads.com/@someone/post/Repost1'],
        },
        profile,
        cap=None,
    )
    assert merged == [
        {'post_url': 'https://www.threads.com/@dlmjhfra/post/Own1', 'source_tab': 'threads'},
        {'post_url': 'https://www.threads.com/@dlmjhfra/post/Reply1', 'source_tab': 'replies'},
        {'post_url': 'https://www.threads.com/@someone/post/Repost1', 'source_tab': 'reposts'},
    ]


def test_is_own_post_detects_profile_handle():
    from platforms.threads.posts_sb import is_own_post

    profile = 'https://www.threads.com/@dlmjhfra/'
    assert is_own_post('https://www.threads.com/@dlmjhfra/post/Aaa1', profile) is True
    assert is_own_post('https://www.threads.com/@someone/post/Repost1', profile) is False


def test_own_post_urls_keeps_only_profile_handle():
    from platforms.threads.posts_sb import own_post_urls

    urls = [
        'https://www.threads.com/@dlmjhfra/post/Aaa1',
        'https://www.threads.com/@other/post/Bbb2',
        'https://www.threads.com/@dlmjhfra/post/Ccc3',
    ]
    own = own_post_urls(urls, 'https://www.threads.com/@dlmjhfra/')
    assert own == [
        'https://www.threads.com/@dlmjhfra/post/Aaa1',
        'https://www.threads.com/@dlmjhfra/post/Ccc3',
    ]


def test_apply_post_cap_none_keeps_all():
    from platforms.threads.posts_sb import apply_post_cap

    urls = [f'https://www.threads.com/@u/post/{i}' for i in range(60)]
    assert len(apply_post_cap(urls, None)) == 60
    assert len(apply_post_cap(urls, 0)) == 60
    assert apply_post_cap(urls, 10) == urls[:10]


def test_collect_until_idle_scrolls_past_twenty():
    from platforms.threads.posts_sb import collect_until_idle

    batches = []
    for n in range(1, 30):
        batches.append([f'https://www.threads.com/@u/post/{i}' for i in range(n)])
    # then freeze
    batches.extend([[f'https://www.threads.com/@u/post/{i}' for i in range(29)]] * 5)

    def collect_fn():
        return batches.pop(0) if batches else [f'https://www.threads.com/@u/post/{i}' for i in range(29)]

    scrolls = {'n': 0}
    urls, rounds = collect_until_idle(
        collect_fn,
        scroll_fn=lambda: scrolls.__setitem__('n', scrolls['n'] + 1),
        sleep_fn=lambda: None,
        max_rounds=200,
        max_idle=4,
        cap=None,
    )
    assert len(urls) == 29
    assert rounds > 20
    assert scrolls['n'] >= 20


def test_merge_replies_drops_empty_duplicate_keeps_comment_text():
    from platforms.threads.posts_sb import _merge_interactors

    base = [{
        'name': 'nurulfatiahmohhatta',
        'profile_url': 'https://www.threads.com/@nurulfatiahmohhatta/',
        'comment_text': 'pukul berapa buka?',
    }]
    extra = [{
        'name': 'nurulfatiahmohhatta',
        'profile_url': 'https://www.threads.com/@nurulfatiahmohhatta/',
        'comment_text': '',
    }, {
        'name': 'emaeriaem',
        'profile_url': 'https://www.threads.com/@emaeriaem/',
        'comment_text': 'lokasi exact mana tu',
    }]
    merged = _merge_interactors(base, extra, with_text=True)
    by_user = {r['profile_url']: r['comment_text'] for r in merged}
    assert by_user['https://www.threads.com/@nurulfatiahmohhatta/'] == 'pukul berapa buka?'
    assert by_user['https://www.threads.com/@emaeriaem/'] == 'lokasi exact mana tu'
    assert len(merged) == 2


def test_parse_reply_name_uses_username_not_full_name():
    from platforms.threads.posts_sb import parse_post_from_html

    html = '''
    <script type="application/json">
    {"thread_items":[
      {"post":{"code":"AaBbCcDd","caption":{"text":"stall"},
        "user":{"username":"dlmjhfra","full_name":"Food Stall"},
        "text_post_app_info":{"direct_reply_count":1,"repost_count":0}}},
      {"post":{"code":"ReplyOne","caption":{"text":"pukul berapa buka?"},
        "user":{"username":"nurulfatiahmohhatta","full_name":"Nurul Fatiah"}}}
    ]}
    </script>
    '''
    result = parse_post_from_html(html, POST_URL)
    assert result['replies'][0]['name'] == 'nurulfatiahmohhatta'
    assert result['replies'][0]['comment_text'] == 'pukul berapa buka?'
    assert result['replies'][0]['profile_url'] == 'https://www.threads.com/@nurulfatiahmohhatta/'


def test_expand_replies_until_exhausted_keeps_going_past_six_rounds():
    from platforms.threads.posts_sb import expand_replies_until_exhausted

    clicks = [3, 2, 2, 1, 1, 1, 1, 1, 0, 0, 0]
    expand_calls = {'n': 0}
    counts = [1, 3, 5, 8, 12, 16, 20, 24, 25, 25, 25]

    def expand_fn():
        expand_calls['n'] += 1
        return clicks.pop(0) if clicks else 0

    def count_fn():
        return counts.pop(0) if counts else 25

    rounds = expand_replies_until_exhausted(
        expand_fn,
        scroll_fn=lambda: None,
        count_fn=count_fn,
        sleep_fn=lambda: None,
        max_rounds=80,
        max_idle=3,
    )

    assert expand_calls['n'] > 6
    assert rounds > 6


def test_expand_replies_until_exhausted_stops_when_idle():
    from platforms.threads.posts_sb import expand_replies_until_exhausted

    expand_calls = {'n': 0}

    def expand_fn():
        expand_calls['n'] += 1
        return 0

    rounds = expand_replies_until_exhausted(
        expand_fn,
        scroll_fn=lambda: None,
        count_fn=lambda: 4,
        sleep_fn=lambda: None,
        max_rounds=80,
        max_idle=3,
    )

    assert expand_calls['n'] == 4
    assert rounds == 4


def test_expand_replies_until_exhausted_stops_at_target_count():
    from platforms.threads.posts_sb import expand_replies_until_exhausted

    expand_calls = {'n': 0}

    def expand_fn():
        expand_calls['n'] += 1
        return 5

    rounds = expand_replies_until_exhausted(
        expand_fn,
        scroll_fn=lambda: None,
        count_fn=lambda: 12,
        sleep_fn=lambda: None,
        max_rounds=80,
        max_idle=3,
        target_count=10,
    )

    assert rounds == 1
    assert expand_calls['n'] == 1


def test_parse_post_from_html_extracts_caption_replies_and_media():
    from platforms.threads.posts_sb import parse_post_from_html

    html_path = os.path.join(FIXTURES, 'threads_post_snippet.html')
    with open(html_path, encoding='utf-8') as f:
        html = f.read()

    result = parse_post_from_html(html, POST_URL)

    assert result['post_url'] == POST_URL
    assert result['caption'] == 'hello world'
    assert result['date'] == '2024-07-01'
    assert result['media_type'] == 'image'
    assert result['image_src'] == 'https://cdn.example/img.jpg'
    assert len(result['replies']) == 2
    names = {r['name'] for r in result['replies']}
    assert names == {'alice', 'bob'}
    assert any(r['comment_text'] == 'nice post' for r in result['replies'])
