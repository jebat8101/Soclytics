import os
from flask import Flask, redirect

from core.db_base import migrate_legacy_fb_db
from platforms.facebook.blueprint import facebook_bp
from platforms.facebook.db import init_db as init_fb_db
from platforms.facebook.constants import BASE_DIR, DB_FILE as FB_DB_FILE
from platforms.instagram.blueprint import instagram_bp
from platforms.instagram.db import init_db as init_ig_db
from platforms.instagram.constants import DB_FILE as IG_DB_FILE
from platforms.reddit.blueprint import reddit_bp
from platforms.reddit.db import init_db as init_reddit_db
from platforms.reddit.constants import DB_FILE as REDDIT_DB_FILE
from platforms.threads.blueprint import threads_bp
from platforms.threads.db import init_db as init_threads_db
from platforms.threads.constants import DB_FILE as THREADS_DB_FILE
from platforms.telegram.blueprint import telegram_bp
from platforms.telegram.db import init_db as init_tg_db
from platforms.telegram.constants import DB_FILE as TG_DB_FILE
from platforms.x.blueprint import x_bp
from platforms.x.db import init_db as init_x_db
from platforms.x.constants import DB_FILE as X_DB_FILE


def create_app():
    migrate_legacy_fb_db(BASE_DIR)
    init_fb_db(FB_DB_FILE)
    init_ig_db(IG_DB_FILE)
    init_reddit_db(REDDIT_DB_FILE)
    init_threads_db(THREADS_DB_FILE)
    init_tg_db(TG_DB_FILE)
    init_x_db(X_DB_FILE)
    application = Flask(
        __name__,
        template_folder=os.path.join(BASE_DIR, 'templates'),
        static_folder=os.path.join(BASE_DIR, 'static'),
    )
    application.secret_key = os.environ.get('SECRET_KEY') or os.urandom(32)
    application.config['TEMPLATES_AUTO_RELOAD'] = True
    application.jinja_env.auto_reload = True
    application.register_blueprint(facebook_bp)
    application.register_blueprint(instagram_bp)
    application.register_blueprint(reddit_bp)
    application.register_blueprint(threads_bp)
    application.register_blueprint(telegram_bp)
    application.register_blueprint(x_bp)

    @application.route('/')
    def root():
        return redirect('/facebook/')

    return application


app = create_app()

def _pick_port(preferred=5000, attempts=20):
    """Return preferred port if free, else the next free port."""
    import socket

    start = int(os.environ.get('PORT', preferred))
    for port in range(start, start + attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(('0.0.0.0', port))
                return port
            except OSError:
                continue
    raise OSError(f'No free port in range {start}-{start + attempts - 1}')


if __name__ == '__main__':
    import sys

    RED = '\033[0;31m'
    CYAN = '\033[0;36m'
    YELLOW = '\033[1;33m'
    RESET = '\033[0m'

    port = _pick_port(5000)
    try:
        print()
        print(f"{RED}██████╗ ██╗██████╗ ██████╗ ██╗   ██╗      ███████╗██████╗ ██╗    ██╗ █████╗ ██████╗ ██████╗ ███████╗{RESET}")
        print(f"{RED}██╔══██╗██║██╔══██╗██╔══██╗╚██╗ ██╔╝      ██╔════╝██╔══██╗██║    ██║██╔══██╗██╔══██╗██╔══██╗██╔════╝{RESET}")
        print(f"{RED}██████╔╝██║██████╔╝██║  ██║ ╚████╔╝ █████╗█████╗  ██║  ██║██║ █╗ ██║███████║██████╔╝██║  ██║███████╗{RESET}")
        print(f"{RED}██╔══██╗██║██╔══██╗██║  ██║  ╚██╔╝  ╚════╝██╔══╝  ██║  ██║██║███╗██║██╔══██║██╔══██╗██║  ██║╚════██║{RESET}")
        print(f"{RED}██████╔╝██║██║  ██║██████╔╝   ██║         ███████╗██████╔╝╚███╔███╔╝██║  ██║██║  ██║██████╔╝███████║{RESET}")
        print(f"{RED}╚═════╝ ╚═╝╚═╝  ╚═╝╚═════╝    ╚═╝         ╚══════╝╚═════╝  ╚══╝╚══╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝ ╚══════╝{RESET}")
        print()
        print(f"{YELLOW}                        Beyond The Metrics — Setup v1.0{RESET}")
        print(f"{CYAN}                        Developed by Jeet Ganguly{RESET}")
        print(f"Visit -> http://127.0.0.1:{port}")
        if port != int(os.environ.get('PORT', 5000)):
            print(f"{YELLOW}Requested port was busy — using {port} instead (or set PORT=...).{RESET}")
    except KeyboardInterrupt:
        sys.exit(0)

    app.run(debug=False, host='0.0.0.0', port=port, threaded=True)
