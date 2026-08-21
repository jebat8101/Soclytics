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

from core.browser import load_cookies_pickle, save_cookies_pickle
from core.date_filters import normalize_date_range
from core.paths import safe_under
from platforms.facebook.constants import (
    BASE_DIR, COOKIE_FILE, DB_FILE, ICONS_DIR, FACE_DIR,
    DEPTH_LIMITS, PIPELINE_STEPS,
)
from platforms.facebook.db import import_all, compute_frequency, extract_top7
from platforms.facebook.about_sb import main as scrape_about
from platforms.facebook.photos_sb import main as scrape_photos
from platforms.facebook.reels_sb import main as scrape_reels
from platforms.facebook.posts_sb import main as scrape_posts

from core.engagement_metrics import get_activity_metrics
from core.pipeline import make_pipeline_state, reset_pipeline, set_step, finish_pipeline
from core.report_routes import register_report_routes
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

try:
    from core.face import run_face_clustering
    FACE_AVAILABLE = True
except ImportError:
    FACE_AVAILABLE = False

os.makedirs(ICONS_DIR, exist_ok=True)
os.makedirs(FACE_DIR, exist_ok=True)

pipeline_state = make_pipeline_state(PIPELINE_STEPS)

facebook_bp = Blueprint('facebook', __name__, url_prefix='/facebook')
register_report_routes(facebook_bp, DB_FILE, 'facebook')


@facebook_bp.route('/')
def home():
    cookie_status = _check_cookie_status_fast()
    return render_template('facebook/index.html', cookie_status=cookie_status)


@facebook_bp.route('/analysis')
def analysis():
    profile_id = request.args.get('id', type=int)
    if not profile_id:
        return redirect(url_for('facebook.home'))
    profile = get_profile_summary(DB_FILE, profile_id)
    if not profile:
        return redirect(url_for('facebook.home'))
    return render_template('facebook/analysis.html', profile=profile, profile_id=profile_id)


@facebook_bp.route('/api/import-cookies', methods=['POST'])
def import_cookies():
    """
    Receive cookie JSON from Cookie-Editor extension,
    convert to pickle format and save as fb_cookies.pkl.
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

        names = [c.get('name', '') for c in cookies]
        if 'c_user' not in names:
            return jsonify({
                'ok': False,
                'error': 'Missing c_user cookie — make sure you are logged into Facebook before exporting'
            })

        converted = []
        for c in cookies:
            selenium_cookie = {
                'name':     c.get('name', ''),
                'value':    c.get('value', ''),
                'domain':   c.get('domain', '.facebook.com'),
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


@facebook_bp.route('/api/check-cookies')
def check_cookies():
    """Fast check — file exists + readable. No Selenium, instant response."""
    status = _check_cookie_status_fast()
    return jsonify({
        'exists': status['exists'],
        'count':  status['count'],
        'error':  status['error'],
    })


@facebook_bp.route('/api/verify-session')
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
                    sb.open('https://www.facebook.com')
                    time.sleep(2)
                    for c in fast['cookies']:
                        try:
                            sb.driver.add_cookie({
                                'name':   c.get('name', ''),
                                'value':  c.get('value', ''),
                                'domain': c.get('domain', '.facebook.com'),
                            })
                        except Exception:
                            pass
                    sb.driver.refresh()
                    time.sleep(4)
                    cur_url = sb.driver.current_url
                    if 'login' in cur_url or 'checkpoint' in cur_url:
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
        return jsonify({'ok': True, 'valid': True, 'error': None,
                        'note': 'Selenium unavailable — skipped check'})


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
        return {'exists': True, 'count': len(cookies), 'cookies': cookies, 'error': None}
    except Exception as e:
        return {'exists': True, 'count': 0, 'cookies': [],
                'error': f'Cannot read cookie file: {e}'}


@facebook_bp.route('/api/investigations')
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
                (SELECT COALESCE(SUM(like_count),0) FROM photo_posts WHERE profile_id=p.id)
                + (SELECT COALESCE(SUM(like_count),0) FROM reel_posts WHERE profile_id=p.id)
                + (SELECT COALESCE(SUM(like_count),0) FROM text_posts WHERE profile_id=p.id) AS like_count,
                (SELECT COALESCE(SUM(reply_count),0) FROM photo_posts WHERE profile_id=p.id)
                + (SELECT COALESCE(SUM(reply_count),0) FROM reel_posts WHERE profile_id=p.id)
                + (SELECT COALESCE(SUM(reply_count),0) FROM text_posts WHERE profile_id=p.id) AS reply_count,
                (SELECT COALESCE(SUM(repost_count),0) FROM photo_posts WHERE profile_id=p.id)
                + (SELECT COALESCE(SUM(repost_count),0) FROM reel_posts WHERE profile_id=p.id)
                + (SELECT COALESCE(SUM(repost_count),0) FROM text_posts WHERE profile_id=p.id) AS repost_count,
                (SELECT COUNT(DISTINCT commentor_id) FROM commentor_frequency
                 WHERE profile_id = p.id) AS interactor_count,
                (SELECT COUNT(*) FROM detected_faces df
                 JOIN photo_posts pp ON pp.id = df.photo_post_id
                 WHERE pp.profile_id = p.id) AS face_count
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
                'like_count':       r['like_count'] or 0,
                'reply_count':      r['reply_count'] or 0,
                'repost_count':     r['repost_count'] or 0,
                'interactor_count': r['interactor_count'] or 0,
                'face_count':       r['face_count'] or 0,
            }
            for r in rows
        ]})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@facebook_bp.route('/api/investigations/<int:profile_id>', methods=['DELETE'])
def delete_investigation(profile_id):
    """
    Completely purge all data for a given profile_id.
    """
    import sqlite3

    if not profile_id:
        return jsonify({'ok': False, 'error': 'profile_id required'}), 400

    try:
        con = sqlite3.connect(DB_FILE)
        cur = con.cursor()

        cur.execute("""
            SELECT df.face_image_path
            FROM detected_faces df
            JOIN photo_posts pp ON pp.id = df.photo_post_id
            WHERE pp.profile_id = ? AND df.face_image_path IS NOT NULL
        """, (profile_id,))
        face_paths = [row[0] for row in cur.fetchall()]

        cur.execute("""
            SELECT DISTINCT df.person_id
            FROM detected_faces df
            JOIN photo_posts pp ON pp.id = df.photo_post_id
            WHERE pp.profile_id = ? AND df.person_id IS NOT NULL
        """, (profile_id,))
        cluster_ids = [row[0] for row in cur.fetchall()]

        cur.execute("""
            DELETE FROM detected_faces
            WHERE photo_post_id IN (
                SELECT id FROM photo_posts WHERE profile_id = ?
            )
        """, (profile_id,))

        if cluster_ids:
            placeholders = ','.join('?' * len(cluster_ids))
            cur.execute(f"""
                DELETE FROM face_clusters
                WHERE id IN ({placeholders})
                AND id NOT IN (SELECT DISTINCT person_id FROM detected_faces WHERE person_id IS NOT NULL)
            """, cluster_ids)

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

        deleted_files = 0
        for rel_path in face_paths:
            if not rel_path:
                continue
            full = os.path.join(BASE_DIR, rel_path.lstrip('/'))
            if os.path.exists(full):
                try:
                    os.remove(full)
                    deleted_files += 1
                except Exception:
                    pass

        return jsonify({
            'ok': True,
            'message': f'Investigation #{profile_id} deleted',
            'face_files_removed': deleted_files,
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({'ok': False, 'error': str(e)}), 500


@facebook_bp.route('/api/start-pipeline', methods=['POST'])
def start_pipeline():
    if pipeline_state['running']:
        return jsonify({'ok': False, 'error': 'Pipeline already running'}), 409

    data        = request.get_json(silent=True) or {}
    profile_url = data.get('profile_url', '').strip()
    depth       = data.get('depth', 'light').strip().lower()
    start_date  = (data.get('start_date') or '').strip() or None
    end_date    = (data.get('end_date') or '').strip() or None

    if not profile_url:
        return jsonify({'ok': False, 'error': 'profile_url required'}), 400
    if depth not in DEPTH_LIMITS:
        depth = 'light'
    try:
        start_date, end_date = normalize_date_range(start_date, end_date)
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400

    status = _check_cookie_status_fast()
    if not status['exists'] or status['count'] == 0:
        return jsonify({'ok': False,
                        'error': 'Cookie file not found — import cookies first'}), 400

    reset_pipeline(
        pipeline_state,
        PIPELINE_STEPS,
        profile_url=profile_url,
        depth=depth,
        start_date=start_date,
        end_date=end_date,
    )
    pipeline_state['running']    = True
    pipeline_state['started_at'] = datetime.now().isoformat()

    threading.Thread(
        target=_run_pipeline,
        args=(profile_url, depth, start_date, end_date),
        daemon=True,
    ).start()
    return jsonify({'ok': True, 'message': 'Pipeline started'})


@facebook_bp.route('/api/pipeline-status')
def pipeline_status():
    return jsonify({
        'ok':          True,
        'running':     pipeline_state['running'],
        'profile_url': pipeline_state['profile_url'],
        'depth':       pipeline_state['depth'],
        'start_date':  pipeline_state['start_date'],
        'end_date':    pipeline_state['end_date'],
        'steps':       pipeline_state['steps'],
        'error':       pipeline_state['error'],
        'profile_id':  pipeline_state['profile_id'],
        'started_at':  pipeline_state['started_at'],
        'finished_at': pipeline_state['finished_at'],
    })


def _run_pipeline(profile_url, depth, start_date=None, end_date=None):
    import multiprocessing, random

    limits       = DEPTH_LIMITS[depth]
    posts_limit  = limits['posts']
    reels_limit  = limits['reels']
    photos_limit = limits['photos']

    def _staggered(delay_s, fn, kwargs):
        """Sleep, then run a scraper. Used as multiprocessing target."""
        time.sleep(delay_s + random.uniform(0, 1.0))
        fn(**kwargs)

    try:
        set_step(pipeline_state, 'about',  'active')
        set_step(pipeline_state, 'photos', 'active')
        set_step(pipeline_state, 'reels',  'active')
        set_step(pipeline_state, 'posts',  'active')

        p1 = multiprocessing.Process(
            target=_staggered,
            args=(0, scrape_about, {'PROFILE_URL': profile_url}),
            name='scrape-about'
        )
        p2 = multiprocessing.Process(
            target=_staggered,
            args=(2, scrape_photos, {
                'PROFILE_URL': profile_url,
                'MAX_PHOTOS': photos_limit,
                'START_DATE': start_date,
                'END_DATE': end_date,
            }),
            name='scrape-photos'
        )
        p3 = multiprocessing.Process(
            target=_staggered,
            args=(4, scrape_reels, {
                'PROFILE_URL': profile_url,
                'MAX_REELS': reels_limit,
                'START_DATE': start_date,
                'END_DATE': end_date,
            }),
            name='scrape-reels'
        )
        p4 = multiprocessing.Process(
            target=_staggered,
            args=(6, scrape_posts, {
                'profile_url': profile_url,
                'max_posts': posts_limit,
                'start_date': start_date,
                'end_date': end_date,
            }),
            name='scrape-posts'
        )

        for p in [p1, p2, p3, p4]:
            p.start()

        for p, step_id in [(p1, 'about'), (p2, 'photos'), (p3, 'reels'), (p4, 'posts')]:
            p.join()
            if p.exitcode == 0:
                set_step(pipeline_state, step_id, 'done')
            else:
                set_step(pipeline_state, step_id, 'error')
                print(f'[PIPELINE] {step_id} exited with code {p.exitcode}')

        set_step(pipeline_state, 'db', 'active')
        try:
            import_all(
                about_json  = os.path.join(BASE_DIR, 'fb_about.json'),
                photos_json = os.path.join(BASE_DIR, 'fb_photos.json'),
                reels_json  = os.path.join(BASE_DIR, 'fb_reels.json'),
                posts_json  = os.path.join(BASE_DIR, 'fb_posts.json'),
                db_file     = DB_FILE,
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

        set_step(pipeline_state, 'face', 'active')
        try:
            if FACE_AVAILABLE:
                run_face_clustering(DB_FILE, profile_id, face_dir=FACE_DIR)
            set_step(pipeline_state, 'face', 'done')
        except Exception as e:
            _step_error('face', e)

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
            about_file = os.path.join(BASE_DIR, 'fb_about.json')
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


@facebook_bp.route('/api/profile-summary/<int:profile_id>')
def api_profile_summary(profile_id):
    try:
        return jsonify({'ok': True, 'data': get_profile_summary(DB_FILE, profile_id)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@facebook_bp.route('/api/all-interactors/<int:profile_id>')
def api_all_interactors(profile_id):
    try:
        return jsonify({'ok': True, 'data': get_all_interactors(DB_FILE, profile_id)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@facebook_bp.route('/api/top7/<int:profile_id>')
def api_top7(profile_id):
    try:
        return jsonify({'ok': True, 'data': get_top7(DB_FILE, profile_id)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@facebook_bp.route('/api/graph-data/<int:profile_id>')
def api_graph_data(profile_id):
    try:
        return jsonify({'ok': True, 'data': get_graph_data(DB_FILE, profile_id)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@facebook_bp.route('/api/cocomment-graph/<int:profile_id>')
def api_cocomment_graph(profile_id):
    try:
        return jsonify({'ok': True, 'data': get_cocomment_graph(DB_FILE, profile_id)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@facebook_bp.route('/api/timeline/<int:profile_id>')
def api_timeline(profile_id):
    try:
        return jsonify({'ok': True, 'data': get_interaction_timeline(DB_FILE, profile_id)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@facebook_bp.route('/api/activity-metrics/<int:profile_id>')
def api_activity_metrics(profile_id):
    try:
        return jsonify({'ok': True, 'data': get_activity_metrics(DB_FILE, profile_id)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@facebook_bp.route('/api/post-type-counts/<int:profile_id>')
def api_post_type_counts(profile_id):
    try:
        return jsonify({'ok': True, 'data': get_post_type_counts(DB_FILE, profile_id)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@facebook_bp.route('/api/face-clusters/<int:profile_id>')
def api_face_clusters(profile_id):
    import sqlite3
    try:
        con = sqlite3.connect(DB_FILE)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute("""
            SELECT DISTINCT fc.id, fc.person_label, fc.representative_face,
                            fc.appearance_count, fc.post_ids, fc.created_at
            FROM face_clusters fc
            WHERE fc.id IN (
                SELECT DISTINCT df.person_id
                FROM detected_faces df
                LEFT JOIN photo_posts pp ON pp.id = df.photo_post_id
                LEFT JOIN text_posts  tp ON tp.id = df.text_post_id
                WHERE df.person_id IS NOT NULL
                  AND (pp.profile_id = ? OR tp.profile_id = ?)
            )
            ORDER BY fc.appearance_count DESC
        """, (profile_id, profile_id))
        rows = [dict(r) for r in cur.fetchall()]
        con.close()
        return jsonify({'ok': True, 'data': rows})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@facebook_bp.route('/api/face-cluster/<int:cluster_id>/members')
def api_face_cluster_members(cluster_id):
    import sqlite3
    try:
        con = sqlite3.connect(DB_FILE)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute("""
            SELECT id, photo_post_id, text_post_id,
                   face_index, face_image_path, person_id
            FROM detected_faces
            WHERE person_id = ?
            ORDER BY id
        """, (cluster_id,))
        rows = [dict(r) for r in cur.fetchall()]
        con.close()
        return jsonify({'ok': True, 'data': rows})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@facebook_bp.route('/logo')
def serve_logo():
    """Serve icons/logo.png"""
    logo = os.path.join(BASE_DIR, 'icons', 'logo.png')
    if os.path.exists(logo):
        return send_file(logo, mimetype='image/png')
    import base64
    px = base64.b64decode('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7')
    return Response(px, mimetype='image/gif')

@facebook_bp.route('/threat')
def serve_icon():
    logo = os.path.join(BASE_DIR, 'icons', 'search1.png')
    if os.path.exists(logo):
        return send_file(logo, mimetype='image/png')
    import base64
    px = base64.b64decode('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7')
    return Response(px, mimetype='image/gif')

@facebook_bp.route('/user')
def serve_user():
    logo = os.path.join(BASE_DIR, 'icons', 'spy.png')
    if os.path.exists(logo):
        return send_file(logo, mimetype='image/jpeg')
    import base64
    px = base64.b64decode('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7')
    return Response(px, mimetype='image/gif')

@facebook_bp.route('/face-image/<path:filepath>')
def face_image(filepath):
    """Serve face crop images from face_data/"""
    try:
        full = safe_under(BASE_DIR, filepath)
    except ValueError:
        return '', 404
    if os.path.exists(full):
        return send_file(full)
    return '', 404

@facebook_bp.route('/api/photo-posts/<int:profile_id>')
def api_photo_posts(profile_id):
    import sqlite3
    try:
        con = sqlite3.connect(DB_FILE)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute("""
            SELECT
                pp.id, pp.photo_url, pp.image_src, pp.caption, pp.date_text,
                COUNT(pc.id) AS interaction_count,
                COALESCE(pp.like_count, 0) AS like_count,
                COALESCE(pp.reply_count, 0) AS reply_count,
                COALESCE(pp.repost_count, 0) AS repost_count
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


@facebook_bp.route('/api/text-posts/<int:profile_id>')
def api_text_posts(profile_id):
    import sqlite3
    try:
        con = sqlite3.connect(DB_FILE)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute("""
            SELECT
                tp.id, tp.post_url, tp.screenshot_path, tp.date_text,
                COUNT(tc.id) AS interaction_count,
                COALESCE(tp.like_count, 0) AS like_count,
                COALESCE(tp.reply_count, 0) AS reply_count,
                COALESCE(tp.repost_count, 0) AS repost_count
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


@facebook_bp.route('/api/reel-posts/<int:profile_id>')
def api_reel_posts(profile_id):
    import sqlite3
    try:
        con = sqlite3.connect(DB_FILE)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute("""
            SELECT
                rp.id, rp.reel_url, rp.scraped_at,
                COUNT(rc.id) AS interaction_count,
                COALESCE(rp.like_count, 0) AS like_count,
                COALESCE(rp.reply_count, 0) AS reply_count,
                COALESCE(rp.repost_count, 0) AS repost_count
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

@facebook_bp.route('/screenshot/<path:filepath>')
def serve_screenshot(filepath):
    try:
        full = safe_under(BASE_DIR, filepath)
    except ValueError:
        return '', 404
    if os.path.exists(full):
        return send_file(full)
    return '', 404
