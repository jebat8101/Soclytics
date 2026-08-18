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
