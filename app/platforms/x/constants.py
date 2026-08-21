import os

# app/platforms/x/constants.py -> three dirname ups = app/
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT_DIR = os.path.dirname(BASE_DIR)
ICONS_DIR = os.path.join(BASE_DIR, 'icons')
COOKIE_FILE = os.path.join(BASE_DIR, 'x_cookies.pkl')
DB_FILE = os.path.join(BASE_DIR, 'socmint_x.db')
FACE_DIR = os.path.join(BASE_DIR, 'face_data_x')

DEPTH_LIMITS = {
    'light': {'posts': 5},
    'medium': {'posts': 10},
    'deep': {'posts': None},  # unlimited; optional date range filters after
}

PIPELINE_STEPS = [
    {'id': 'about', 'label': 'Scraping - Profile'},
    {'id': 'posts', 'label': 'Scraping - Posts + Counts'},
    {'id': 'db', 'label': 'Database Import'},
    {'id': 'frequency', 'label': 'Frequency Scoring'},
    {'id': 'top7', 'label': 'Top 7 Metadata Gather'},
    {'id': 'face', 'label': 'Face Clustering'},
]
