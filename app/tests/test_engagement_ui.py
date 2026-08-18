from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'templates'
PLATFORMS = ('facebook', 'instagram', 'reddit', 'threads', 'telegram', 'x')


def test_analysis_has_activity_metrics_and_stat_likes():
    for name in PLATFORMS:
        text = (ROOT / name / 'analysis.html').read_text(encoding='utf-8')
        assert 'activity-metrics' in text, name
        assert 'statLikes' in text, name


def test_fb_ig_threads_analysis_use_x_tweet_feed():
    for name in ('facebook', 'instagram', 'threads'):
        text = (ROOT / name / 'analysis.html').read_text(encoding='utf-8')
        assert 'class="x-feed"' in text, name
        assert 'class="x-tweet"' in text, name
        assert 'engagementMetricsHtml(p, false)' in text, name
        assert 'engagementMetricsHtml(p, true)' not in text, name


def _threads_scan_desc(depth: str) -> str:
    import re
    text = (ROOT / 'threads' / 'index.html').read_text(encoding='utf-8')
    match = re.search(
        rf'id="depth-{depth}"[\s\S]*?<span class="scan-desc">(.*?)</span>',
        text,
    )
    assert match, depth
    return match.group(1)


def test_threads_light_medium_scan_setup_matches_deep_tabs():
    tabs = ('Threads', 'Replies', 'Media', 'Reposts')
    light = _threads_scan_desc('light')
    medium = _threads_scan_desc('medium')
    deep = _threads_scan_desc('deep')
    for name in tabs:
        assert name in deep, name
        assert name in light, name
        assert name in medium, name
    assert '5 posts' in light
    assert '10 posts' in medium
    assert 'reels' not in light.lower()
    assert 'photos' not in light.lower()
    assert 'reels' not in medium.lower()
    assert 'photos' not in medium.lower()
