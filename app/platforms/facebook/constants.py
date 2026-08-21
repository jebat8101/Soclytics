import os

# app/platforms/facebook/constants.py → three dirname ups = app/
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT_DIR = os.path.dirname(BASE_DIR)
ICONS_DIR = os.path.join(BASE_DIR, 'icons')
COOKIE_FILE = os.path.join(BASE_DIR, 'fb_cookies.pkl')
DB_FILE = os.path.join(BASE_DIR, 'socmint_fb.db')
FACE_DIR = os.path.join(BASE_DIR, 'face_data')

DEPTH_LIMITS = {
    'light':  {'posts': 5,  'reels': 5,  'photos': 5},
    'medium': {'posts': 10, 'reels': 10, 'photos': 10},
    'deep':   {'posts': None, 'reels': None, 'photos': None},  # unlimited
}

PIPELINE_STEPS = [
    {'id': 'about',     'label': 'Scraping — About / Profile Info'},
    {'id': 'photos',    'label': 'Scraping — Photos + Comments'},
    {'id': 'reels',     'label': 'Scraping — Reels + Comments'},
    {'id': 'posts',     'label': 'Scraping — Posts + Comments'},
    {'id': 'db',        'label': 'Database Import'},
    {'id': 'frequency', 'label': 'Frequency Scoring'},
    {'id': 'top7',      'label': 'Top 7 Metadata Gather'},
    {'id': 'face',      'label': 'Face Clustering — CNN'},
]
