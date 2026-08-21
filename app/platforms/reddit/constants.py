import os

# app/platforms/reddit/constants.py → three dirname ups = app/
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT_DIR = os.path.dirname(BASE_DIR)
ICONS_DIR = os.path.join(BASE_DIR, 'icons')
COOKIE_FILE = os.path.join(BASE_DIR, 'reddit_cookies.pkl')
DB_FILE = os.path.join(BASE_DIR, 'socmint_reddit.db')

DEPTH_LIMITS = {
    'light':  {'posts': 5},
    'medium': {'posts': 10},
    'deep':   {'posts': None},  # unlimited
}

PIPELINE_STEPS = [
    {'id': 'about',     'label': 'Scraping — Profile'},
    {'id': 'posts',     'label': 'Scraping — Submissions + Comments'},
    {'id': 'db',        'label': 'Database Import'},
    {'id': 'frequency', 'label': 'Frequency Scoring'},
    {'id': 'top7',      'label': 'Top 7 Metadata Gather'},
]
