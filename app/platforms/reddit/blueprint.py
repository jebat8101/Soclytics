import os
import json
import time
import threading
import traceback
from datetime import datetime

from flask import (
    Blueprint, render_template, request, jsonify, redirect, url_for,
    send_file, current_app, Response,
)

from core.browser import (
    load_cookies_pickle, save_cookies_pickle,
    cookies_have_domain, filter_cookies_for_domain,
)
from core.urls import normalize_reddit_target
from core.paths import safe_under
from platforms.reddit.constants import (
    BASE_DIR, COOKIE_FILE, DB_FILE, ICONS_DIR,
    DEPTH_LIMITS, PIPELINE_STEPS,
)
from platforms.reddit.db import import_all, compute_frequency, extract_top7
from platforms.reddit.about_sb import main as scrape_about
from platforms.reddit.submissions_sb import main as scrape_submissions

from core.pipeline import make_pipeline_state, reset_pipeline, set_step, finish_pipeline
from core.scoring import (
    get_profile_id,
    get_all_interactors,
    get_top7,
    get_graph_data,
    get_cocomment_graph,
    get_interaction_timeline,
    get_post_type_counts,
    get_profile_summary,
)

os.makedirs(ICONS_DIR, exist_ok=True)

pipeline_state = make_pipeline_state(PIPELINE_STEPS)

reddit_bp = Blueprint('reddit', __name__, url_prefix='/reddit')


@reddit_bp.route('/')
def home():
    cookie_status = _check_cookie_status_fast()
    return render_template('reddit/index.html', cookie_status=cookie_status)


@reddit_bp.route('/analysis')
def analysis():
    profile_id = request.args.get('id', type=int)
    if not profile_id:
        return redirect(url_for('reddit.home'))
    profile = get_profile_summary(DB_FILE, profile_id)
    if not profile:
        return redirect(url_for('reddit.home'))
    return render_template('reddit/analysis.html', profile=profile, profile_id=profile_id)


@reddit_bp.route('/api/import-cookies', methods=['POST'])
def import_cookies():
    """
    Receive cookie JSON from Cookie-Editor extension,
    convert to pickle format and save as reddit_cookies.pkl.
    """
    import json as _json

    try:
        data = request.get_json()
        if not data:
            return jsonify({'ok': False, 'error': 'No data received'})

        cookies_json = data.get('cookies', '')
        if not cookies_json:
            return jsonify({'ok': False, 'error': 'No cookies provided'})

        if isinstance(cookies_json, str):
            cookies = _json.loads(cookies_json)
        else:
            cookies = cookies_json

        if not isinstance(cookies, list):
            return jsonify({'ok': False, 'error': 'Invalid format — expected JSON array'})

        if len(cookies) == 0:
            return jsonify({'ok': False, 'error': 'Cookie array is empty'})

        if not cookies_have_domain(cookies, 'reddit.com'):
            return jsonify({
                'ok': False,
                'error': 'No Reddit cookies found — export cookies from reddit.com'
            })

        names = [c.get('name', '') for c in cookies]
        if 'reddit_session' not in names and 'token_v2' not in names:
            return jsonify({
                'ok': False,
                'error': 'Missing reddit_session/token_v2 — make sure you are logged into Reddit before exporting'
            })

        rd_cookies = filter_cookies_for_domain(cookies, 'reddit.com')
        converted = []
        for c in rd_cookies:
            selenium_cookie = {
                'name':     c.get('name', ''),
                'value':    c.get('value', ''),
                'domain':   c.get('domain', '.reddit.com'),
                'path':     c.get('path', '/'),
                'httpOnly': c.get('httpOnly', False),
                'secure':   c.get('secure', False),
            }
            expires = c.get('expirationDate') or c.get('expires') or c.get('expiry')
            if expires and isinstance(expires, (int, float)):
                selenium_cookie['expiry'] = int(expires)

            same_site = c.get('sameSite', 'None')
            if same_site in ('Strict', 'Lax', 'None'):
                selenium_cookie['sameSite'] = same_site

            converted.append(selenium_cookie)

        save_cookies_pickle(COOKIE_FILE, converted)
        current_app.config['COOKIES_OK'] = True

        return jsonify({
            'ok': True,
            'count': len(converted),
            'message': f'{len(converted)} cookies imported successfully'
        })

    except _json.JSONDecodeError as e:
        return jsonify({'ok': False, 'error': f'Invalid JSON: {str(e)}'})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@reddit_bp.route('/api/check-cookies')
def check_cookies():
    """Fast check — file exists + readable. No Selenium, instant response."""
    status = _check_cookie_status_fast()
    return jsonify({
        'exists': status['exists'],
        'count':  status['count'],
        'error':  status['error'],
    })


@reddit_bp.route('/api/verify-session')
def verify_session():
    """
    On-demand Selenium session check.
    Only called when user clicks 'Verify Session' button — not on page load.
    """
    fast = _check_cookie_status_fast()
    if not fast['exists'] or fast['count'] == 0:
        return jsonify({'ok': False, 'valid': False,
                        'error': 'No cookies found — import cookies first'})

    try:
        from seleniumbase import SB
        result = {'valid': False, 'error': None}

        def _run():
            try:
                with SB(uc=True, headless=True, xvfb=True) as sb:
                    sb.open('https://www.reddit.com')
                    time.sleep(2)
                    for c in fast['cookies']:
                        try:
                            sb.driver.add_cookie({
                                'name':   c.get('name', ''),
                                'value':  c.get('value', ''),
                                'domain': c.get('domain', '.reddit.com'),
                            })
                        except Exception:
                            pass
                    sb.driver.refresh()
                    time.sleep(4)
                    cur_url = sb.driver.current_url
                    if 'login' in cur_url:
                        result['valid'] = False
                        result['error'] = 'Session expired — please re-import fresh cookies'
                    else:
                        result['valid'] = True
            except Exception as e:
                result['error'] = str(e)

        t = threading.Thread(target=_run)
        t.start()
        t.join(timeout=35)

        return jsonify({'ok': True, 'valid': result['valid'], 'error': result['error']})

    except ImportError:
        return jsonify({'ok': False, 'valid': False,
                        'error': 'SeleniumBase unavailable — cannot verify session'})


def _check_cookie_status_fast():
    """
    Fast cookie status — no Selenium, no network.
    Returns: {exists, count, cookies, error}
    """
    if not os.path.exists(COOKIE_FILE):
        return {'exists': False, 'count': 0, 'cookies': [], 'error': None}
    try:
        cookies = load_cookies_pickle(COOKIE_FILE)
        if not isinstance(cookies, list) or len(cookies) == 0:
            return {'exists': True, 'count': 0, 'cookies': [],
                    'error': 'Cookie file empty or corrupt'}
        if not cookies_have_domain(cookies, 'reddit.com'):
            return {'exists': True, 'count': len(cookies), 'cookies': cookies,
                    'error': 'Cookie file has no Reddit domain cookies'}
        return {'exists': True, 'count': len(cookies), 'cookies': cookies, 'error': None}
    except Exception as e:
        return {'exists': True, 'count': 0, 'cookies': [],
                'error': f'Cannot read cookie file: {e}'}


@reddit_bp.route('/api/investigations')
def get_investigations():
    import sqlite3
    try:
        con = sqlite3.connect(DB_FILE)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute("""
            SELECT
                p.id, p.profile_url, p.owner_name, p.is_locked, p.scraped_at,
                (SELECT COUNT(*) FROM photo_posts WHERE profile_id = p.id) +
                (SELECT COUNT(*) FROM reel_posts  WHERE profile_id = p.id) +
                (SELECT COUNT(*) FROM text_posts  WHERE profile_id = p.id) AS post_count,
                (SELECT COUNT(DISTINCT commentor_id) FROM commentor_frequency
                 WHERE profile_id = p.id) AS interactor_count,
                0 AS face_count
            FROM profiles p
            ORDER BY p.id DESC
        """)
        rows = cur.fetchall()
        con.close()
        return jsonify({'ok': True, 'records': [
            {
                'id':               r['id'],
                'name':             r['owner_name'] or 'Unknown',
                'url':              r['profile_url'],
                'is_locked':        bool(r['is_locked']),
                'scraped_at':       r['scraped_at'] or '',
                'post_count':       r['post_count'] or 0,
                'interactor_count': r['interactor_count'] or 0,
                'face_count':       0,
            }
            for r in rows
        ]})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@reddit_bp.route('/api/investigations/<int:profile_id>', methods=['DELETE'])
def delete_investigation(profile_id):
    """Completely purge all data for a given profile_id."""
    import sqlite3

    if not profile_id:
        return jsonify({'ok': False, 'error': 'profile_id required'}), 400

    try:
        con = sqlite3.connect(DB_FILE)
        cur = con.cursor()

        cur.execute("""
            DELETE FROM detected_faces
            WHERE photo_post_id IN (
                SELECT id FROM photo_posts WHERE profile_id = ?
            )
            OR text_post_id IN (
                SELECT id FROM text_posts WHERE profile_id = ?
            )
        """, (profile_id, profile_id))

        cur.execute("""
            DELETE FROM top7_profile_fields
            WHERE top7_profile_id IN (
                SELECT id FROM top7_profiles WHERE profile_id = ?
            )
        """, (profile_id,))
        cur.execute("DELETE FROM top7_profiles WHERE profile_id = ?", (profile_id,))
        cur.execute("DELETE FROM commentor_frequency WHERE profile_id = ?", (profile_id,))

        cur.execute("""
            DELETE FROM photo_comments
            WHERE photo_post_id IN (SELECT id FROM photo_posts WHERE profile_id = ?)
        """, (profile_id,))
        cur.execute("""
            DELETE FROM reel_comments
            WHERE reel_post_id IN (SELECT id FROM reel_posts WHERE profile_id = ?)
        """, (profile_id,))
        cur.execute("""
            DELETE FROM text_comments
            WHERE text_post_id IN (SELECT id FROM text_posts WHERE profile_id = ?)
        """, (profile_id,))

        cur.execute("DELETE FROM photo_posts WHERE profile_id = ?", (profile_id,))
        cur.execute("DELETE FROM reel_posts  WHERE profile_id = ?", (profile_id,))
        cur.execute("DELETE FROM text_posts  WHERE profile_id = ?", (profile_id,))
        cur.execute("DELETE FROM profile_fields WHERE profile_id = ?", (profile_id,))
        cur.execute("DELETE FROM profiles WHERE id = ?", (profile_id,))

        cur.execute("""
            DELETE FROM commentors
            WHERE id NOT IN (SELECT commentor_id FROM photo_comments)
            AND   id NOT IN (SELECT commentor_id FROM reel_comments)
            AND   id NOT IN (SELECT commentor_id FROM text_comments)
        """)

        con.commit()
        con.close()

        return jsonify({
            'ok': True,
            'message': f'Investigation #{profile_id} deleted',
            'face_files_removed': 0,
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({'ok': False, 'error': str(e)}), 500


@reddit_bp.route('/api/start-pipeline', methods=['POST'])
def start_pipeline():
    if pipeline_state['running']:
        return jsonify({'ok': False, 'error': 'Pipeline already running'}), 409

    data        = request.get_json(silent=True) or {}
    profile_url = data.get('profile_url', '').strip()
    depth       = data.get('depth', 'light').strip().lower()

    if not profile_url:
        return jsonify({'ok': False, 'error': 'profile_url required'}), 400

    try:
        profile_url = normalize_reddit_target(profile_url)
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400

    if depth not in DEPTH_LIMITS:
        depth = 'light'

    status = _check_cookie_status_fast()
    if not status['exists'] or status['count'] == 0:
        return jsonify({'ok': False,
                        'error': 'Cookie file not found — import cookies first'}), 400

    reset_pipeline(pipeline_state, PIPELINE_STEPS, profile_url=profile_url, depth=depth)
    pipeline_state['running']    = True
    pipeline_state['started_at'] = datetime.now().isoformat()

    threading.Thread(target=_run_pipeline, args=(profile_url, depth), daemon=True).start()
    return jsonify({'ok': True, 'message': 'Pipeline started'})


@reddit_bp.route('/api/pipeline-status')
def pipeline_status():
    return jsonify({
        'ok':          True,
        'running':     pipeline_state['running'],
        'profile_url': pipeline_state['profile_url'],
        'depth':       pipeline_state['depth'],
        'steps':       pipeline_state['steps'],
        'error':       pipeline_state['error'],
        'profile_id':  pipeline_state['profile_id'],
        'started_at':  pipeline_state['started_at'],
        'finished_at': pipeline_state['finished_at'],
    })


def _run_pipeline(profile_url, depth):
    import multiprocessing, random

    limits = DEPTH_LIMITS[depth]
    posts_limit = limits['posts']

    def _staggered(delay_s, fn, kwargs):
        """Sleep, then run a scraper. Used as multiprocessing target."""
        time.sleep(delay_s + random.uniform(0, 1.0))
        fn(**kwargs)

    try:
        set_step(pipeline_state, 'about', 'active')
        set_step(pipeline_state, 'posts', 'active')

        p1 = multiprocessing.Process(
            target=_staggered,
            args=(0, scrape_about, {'PROFILE_URL': profile_url}),
            name='scrape-about'
        )
        p2 = multiprocessing.Process(
            target=_staggered,
            args=(2, scrape_submissions, {
                'PROFILE_URL': profile_url,
                'MAX_POSTS': posts_limit,
            }),
            name='scrape-submissions'
        )

        for p in [p1, p2]:
            p.start()

        for p, step_id in [(p1, 'about'), (p2, 'posts')]:
            p.join()
            if p.exitcode == 0:
                set_step(pipeline_state, step_id, 'done')
            else:
                set_step(pipeline_state, step_id, 'error')
                print(f'[PIPELINE] {step_id} exited with code {p.exitcode}')

        set_step(pipeline_state, 'db', 'active')
        try:
            import_all(
                about_json=os.path.join(BASE_DIR, 'reddit_about.json'),
                submissions_json=os.path.join(BASE_DIR, 'reddit_submissions.json'),
                db_file=DB_FILE,
                expected_profile_url=profile_url,
            )
            p = get_profile_id(DB_FILE)
            if p:
                pipeline_state['profile_id'] = p['id']
            set_step(pipeline_state, 'db', 'done')
        except Exception as e:
            _step_error('db', e)
            finish_pipeline(pipeline_state, error=str(e))
            return

        profile_id = pipeline_state['profile_id']

        set_step(pipeline_state, 'frequency', 'active')
        try:
            compute_frequency(DB_FILE, profile_id)
            set_step(pipeline_state, 'frequency', 'done')
        except Exception as e:
            _step_error('frequency', e)

        set_step(pipeline_state, 'top7', 'active')
        try:
            top7 = extract_top7(DB_FILE, profile_id)
            _scrape_top7_about(top7, profile_id)
            set_step(pipeline_state, 'top7', 'done')
        except Exception as e:
            _step_error('top7', e)

        # No face clustering for Reddit
        finish_pipeline(pipeline_state)

    except Exception as e:
        traceback.print_exc()
        finish_pipeline(pipeline_state, error=str(e))


def _scrape_top7_about(top7, profile_id):
    import sqlite3
    for entry in top7:
        url = entry.get('profile_url', '')
        if not url:
            continue
        try:
            scrape_about(PROFILE_URL=url)
            about_file = os.path.join(BASE_DIR, 'reddit_about.json')
            if not os.path.exists(about_file):
                continue
            with open(about_file, encoding='utf-8') as f:
                data = json.load(f)
            sections = data.get('sections', {})
            con = sqlite3.connect(DB_FILE)
            cur = con.cursor()
            cur.execute("""
                SELECT id FROM top7_profiles
                WHERE profile_id = ? AND commentor_id = ?
            """, (profile_id, entry['commentor_id']))
            row = cur.fetchone()
            if not row:
                con.close()
                continue
            t7id = row[0]
            cur.execute("DELETE FROM top7_profile_fields WHERE top7_profile_id = ?", (t7id,))
            for section, fields in sections.items():
                for field in fields:
                    cur.execute("""
                        INSERT INTO top7_profile_fields
                            (top7_profile_id, section, field_type, label, value, sub_label)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (t7id, section, field.get('field_type'), field.get('label'),
                          field.get('value'), field.get('sub_label')))
            con.commit()
            con.close()
        except Exception as e:
            print(f'  [TOP7] {url}: {e}')


def _step_error(step_id, exc):
    set_step(pipeline_state, step_id, 'error')
    print(f'[PIPELINE] {step_id} error: {exc}')


@reddit_bp.route('/api/profile-summary/<int:profile_id>')
def api_profile_summary(profile_id):
    try:
        return jsonify({'ok': True, 'data': get_profile_summary(DB_FILE, profile_id)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@reddit_bp.route('/api/all-interactors/<int:profile_id>')
def api_all_interactors(profile_id):
    try:
        return jsonify({'ok': True, 'data': get_all_interactors(DB_FILE, profile_id)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@reddit_bp.route('/api/top7/<int:profile_id>')
def api_top7(profile_id):
    try:
        return jsonify({'ok': True, 'data': get_top7(DB_FILE, profile_id)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@reddit_bp.route('/api/graph-data/<int:profile_id>')
def api_graph_data(profile_id):
    try:
        return jsonify({'ok': True, 'data': get_graph_data(DB_FILE, profile_id)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@reddit_bp.route('/api/cocomment-graph/<int:profile_id>')
def api_cocomment_graph(profile_id):
    try:
        return jsonify({'ok': True, 'data': get_cocomment_graph(DB_FILE, profile_id)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@reddit_bp.route('/api/timeline/<int:profile_id>')
def api_timeline(profile_id):
    try:
        return jsonify({'ok': True, 'data': get_interaction_timeline(DB_FILE, profile_id)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@reddit_bp.route('/api/post-type-counts/<int:profile_id>')
def api_post_type_counts(profile_id):
    try:
        return jsonify({'ok': True, 'data': get_post_type_counts(DB_FILE, profile_id)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@reddit_bp.route('/api/face-clusters/<int:profile_id>')
def api_face_clusters(profile_id):
    """Reddit has no face step — always return empty payload."""
    return jsonify({'ok': True, 'data': []})


@reddit_bp.route('/api/face-cluster/<int:cluster_id>/members')
def api_face_cluster_members(cluster_id):
    """Reddit has no face step — always return empty payload."""
    return jsonify({'ok': True, 'data': []})


@reddit_bp.route('/logo')
def serve_logo():
    """Serve icons/logo.jpeg"""
    logo = os.path.join(BASE_DIR, 'icons', 'logo.jpeg')
    if os.path.exists(logo):
        return send_file(logo, mimetype='image/jpeg')
    import base64
    px = base64.b64decode('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7')
    return Response(px, mimetype='image/gif')

@reddit_bp.route('/threat')
def serve_icon():
    logo = os.path.join(BASE_DIR, 'icons', 'search.png')
    if os.path.exists(logo):
        return send_file(logo, mimetype='image/jpeg')
    import base64
    px = base64.b64decode('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7')
    return Response(px, mimetype='image/gif')

@reddit_bp.route('/user')
def serve_user():
    logo = os.path.join(BASE_DIR, 'icons', 'spy.png')
    if os.path.exists(logo):
        return send_file(logo, mimetype='image/jpeg')
    import base64
    px = base64.b64decode('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7')
    return Response(px, mimetype='image/gif')

@reddit_bp.route('/api/photo-posts/<int:profile_id>')
def api_photo_posts(profile_id):
    import sqlite3
    try:
        con = sqlite3.connect(DB_FILE)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute("""
            SELECT
                pp.id, pp.photo_url, pp.image_src, pp.caption, pp.date_text,
                COUNT(pc.id) AS interaction_count
            FROM photo_posts pp
            LEFT JOIN photo_comments pc ON pc.photo_post_id = pp.id
            WHERE pp.profile_id = ?
            GROUP BY pp.id
            ORDER BY pp.id DESC
        """, (profile_id,))
        rows = [dict(r) for r in cur.fetchall()]
        con.close()
        return jsonify({'ok': True, 'data': rows})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@reddit_bp.route('/api/text-posts/<int:profile_id>')
def api_text_posts(profile_id):
    import sqlite3
    try:
        con = sqlite3.connect(DB_FILE)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute("""
            SELECT
                tp.id, tp.post_url, tp.screenshot_path, tp.date_text,
                tp.title, tp.subreddit, tp.body,
                COUNT(tc.id) AS interaction_count
            FROM text_posts tp
            LEFT JOIN text_comments tc ON tc.text_post_id = tp.id
            WHERE tp.profile_id = ?
            GROUP BY tp.id
            ORDER BY tp.id DESC
        """, (profile_id,))
        rows = [dict(r) for r in cur.fetchall()]
        con.close()
        return jsonify({'ok': True, 'data': rows})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@reddit_bp.route('/api/reel-posts/<int:profile_id>')
def api_reel_posts(profile_id):
    import sqlite3
    try:
        con = sqlite3.connect(DB_FILE)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute("""
            SELECT
                rp.id, rp.reel_url, rp.scraped_at,
                COUNT(rc.id) AS interaction_count
            FROM reel_posts rp
            LEFT JOIN reel_comments rc ON rc.reel_post_id = rp.id
            WHERE rp.profile_id = ?
            GROUP BY rp.id
            ORDER BY rp.id DESC
        """, (profile_id,))
        rows = [dict(r) for r in cur.fetchall()]
        con.close()
        return jsonify({'ok': True, 'data': rows})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@reddit_bp.route('/screenshot/<path:filepath>')
def serve_screenshot(filepath):
    try:
        full = safe_under(BASE_DIR, filepath)
    except ValueError:
        return '', 404
    if os.path.exists(full):
        return send_file(full)
    return '', 404
