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


def create_app():
    migrate_legacy_fb_db(BASE_DIR)
    init_fb_db(FB_DB_FILE)
    init_ig_db(IG_DB_FILE)
    init_reddit_db(REDDIT_DB_FILE)
    application = Flask(
        __name__,
        template_folder=os.path.join(BASE_DIR, 'templates'),
        static_folder=os.path.join(BASE_DIR, 'static'),
    )
    application.secret_key = os.environ.get('SECRET_KEY') or os.urandom(32)
    application.register_blueprint(facebook_bp)
    application.register_blueprint(instagram_bp)
    application.register_blueprint(reddit_bp)

    @application.route('/')
    def root():
        return redirect('/facebook/')

    return application


app = create_app()

if __name__ == '__main__':
    import sys

    RED = '\033[0;31m'
    CYAN = '\033[0;36m'
    YELLOW = '\033[1;33m'
    RESET = '\033[0m'

    try:
        print()
        print(f"{RED}██████╗ ██╗██████╗ ██████╗ ██╗   ██╗      ███████╗██████╗ ██╗    ██╗ █████╗ ██████╗ ██████╗ ███████╗{RESET}")
        print(f"{RED}██╔══██╗██║██╔══██╗██╔══██╗╚██╗ ██╔╝      ██╔════╝██╔══██╗██║    ██║██╔══██╗██╔══██╗██╔══██╗██╔════╝{RESET}")
        print(f"{RED}██████╔╝██║██████╔╝██║  ██║ ╚████╔╝ █████╗█████╗  ██║  ██║██║ █╗ ██║███████║██████╔╝██║  ██║███████╗{RESET}")
        print(f"{RED}██╔══██╗██║██╔══██╗██║  ██║  ╚██╔╝  ╚════╝██╔══╝  ██║  ██║██║███╗██║██╔══██║██╔══██╗██║  ██║╚════██║{RESET}")
        print(f"{RED}██████╔╝██║██║  ██║██████╔╝   ██║         ███████╗██████╔╝╚███╔███╔╝██║  ██║██║  ██║██████╔╝███████║{RESET}")
        print(f"{RED}╚═════╝ ╚═╝╚═╝  ╚═╝╚═════╝    ╚═╝         ╚══════╝╚═════╝  ╚══╝╚══╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝ ╚══════╝{RESET}")
        print()
        print(f"{YELLOW}                        Infiltrate & Expose — Setup v1.0{RESET}")
        print(f"{CYAN}                        Developed by Jeet Ganguly{RESET}")
        print("Visit -> http://127.0.0.1:5000")
    except KeyboardInterrupt:
        sys.exit(0)

    app.run(debug=False, host='0.0.0.0', port=5000, threaded=True)
