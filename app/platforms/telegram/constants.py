import os

# app/platforms/telegram/constants.py → three dirname ups = app/
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT_DIR = os.path.dirname(BASE_DIR)
ICONS_DIR = os.path.join(BASE_DIR, 'icons')
DB_FILE = os.path.join(BASE_DIR, 'socmint_tg.db')
FACE_DIR = os.path.join(BASE_DIR, 'face_data_tg')
MEDIA_DIR = os.path.join(BASE_DIR, 'telegram_media')
TEXT_DIR = os.path.join(BASE_DIR, 'post_screenshots')

ABOUT_OUT = os.path.join(BASE_DIR, 'telegram_about.json')
PHOTOS_OUT = os.path.join(BASE_DIR, 'telegram_photos.json')
REELS_OUT = os.path.join(BASE_DIR, 'telegram_reels.json')
POSTS_OUT = os.path.join(BASE_DIR, 'telegram_posts.json')

CONFIG_CANDIDATES = (
    os.environ.get('TG_CONFIG'),
    os.path.join(BASE_DIR, 'telegram_config.json'),
    os.path.join(ROOT_DIR, 'telegram_config.json'),
    os.path.join(os.path.dirname(ROOT_DIR), 'telegram_osint', 'config.json'),
)

DEPTH_LIMITS = {
    'light':  {'posts': 5,  'reels': 5,  'photos': 5},
    'medium': {'posts': 10, 'reels': 10, 'photos': 10},
    'deep':   {'posts': 50, 'reels': 50, 'photos': 50},
}

PIPELINE_STEPS = [
    {'id': 'about',     'label': 'Collecting — Profile / About'},
    {'id': 'photos',    'label': 'Collecting — Photos + Interactors'},
    {'id': 'reels',     'label': 'Collecting — Videos + Interactors'},
    {'id': 'posts',     'label': 'Collecting — Text / Day Threads'},
    {'id': 'db',        'label': 'Database Import'},
    {'id': 'frequency', 'label': 'Frequency Scoring'},
    {'id': 'top7',      'label': 'Top 7 Priority Targets'},
    {'id': 'face',      'label': 'Face Clustering — CNN'},
]
