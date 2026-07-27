import json
import os
import threading
import time
import traceback
from datetime import datetime

from flask import (
    Blueprint, Response, current_app, jsonify, redirect, render_template,
    request, send_file, url_for,
)

from core.browser import (
    cookies_have_any_domain, filter_cookies_for_any_domain, load_cookies_pickle,
    save_cookies_pickle,
)
from core.paths import safe_under
from core.pipeline import finish_pipeline, make_pipeline_state, reset_pipeline, set_step
from core.scoring import (
    get_cocomment_graph,
    get_graph_data,
    get_post_type_counts,
    get_profile_id,
    get_profile_summary,
    get_top7,
)
from core.urls import normalize_threads_target
from platforms.threads.about_sb import main as scrape_about
from platforms.threads.constants import (
    BASE_DIR, COOKIE_FILE, DB_FILE, DEPTH_LIMITS, FACE_DIR, ICONS_DIR,
    PIPELINE_STEPS,
)
from platforms.threads.db import compute_frequency, extract_top7, import_all
from platforms.threads.posts_sb import main as scrape_posts

THREADS_COOKIE_DOMAINS = ('threads.com', 'threads.net')
THREADS_HOME = 'https://www.threads.com/'

try:
    from core.face import run_face_clustering
    FACE_AVAILABLE = True
except ImportError:
    FACE_AVAILABLE = False

os.makedirs(ICONS_DIR, exist_ok=True)
os.makedirs(FACE_DIR, exist_ok=True)

pipeline_state = make_pipeline_state(PIPELINE_STEPS)
threads_bp = Blueprint('threads', __name__, url_prefix='/threads')


@threads_bp.route('/')
def home():
    cookie_status = _check_cookie_status_fast()
    return render_template('threads/index.html', cookie_status=cookie_status)


@threads_bp.route('/analysis')
def analysis():
    profile_id = request.args.get('id', type=int)
    if not profile_id:
        return redirect(url_for('threads.home'))
    profile = get_profile_summary(DB_FILE, profile_id)
    if not profile:
        return redirect(url_for('threads.home'))
    return render_template('threads/analysis.html', profile=profile, profile_id=profile_id)


@threads_bp.route('/api/import-cookies', methods=['POST'])
def import_cookies():
    import json as _json

    try:
        data = request.get_json()
        if not data:
            return jsonify({'ok': False, 'error': 'No data received'})

        cookies_json = data.get('cookies', '')
        if not cookies_json:
            return jsonify({'ok': False, 'error': 'No cookies provided'})

        cookies = _json.loads(cookies_json) if isinstance(cookies_json, str) else cookies_json
        if not isinstance(cookies, list):
            return jsonify({'ok': False, 'error': 'Invalid format - expected JSON array'})
        if not cookies:
            return jsonify({'ok': False, 'error': 'Cookie array is empty'})
        if not cookies_have_any_domain(cookies, list(THREADS_COOKIE_DOMAINS)):
            return jsonify({
                'ok': False,
                'error': 'No Threads cookies found - export cookies from threads.com',
            })

        thread_cookies = filter_cookies_for_any_domain(cookies, list(THREADS_COOKIE_DOMAINS))
        converted = []
        for c in thread_cookies:
            domain = c.get('domain') or '.threads.com'
            # Prefer .threads.com when Meta still emits legacy .threads.net cookies.
            if 'threads.net' in domain and 'threads.com' not in domain:
                domain = domain.replace('threads.net', 'threads.com')
            selenium_cookie = {
                'name': c.get('name', ''),
                'value': c.get('value', ''),
                'domain': domain,
                'path': c.get('path', '/'),
                'httpOnly': c.get('httpOnly', False),
                'secure': c.get('secure', False),
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
            'message': f'{len(converted)} cookies imported successfully',
        })
    except _json.JSONDecodeError as e:
        return jsonify({'ok': False, 'error': f'Invalid JSON: {str(e)}'})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@threads_bp.route('/api/check-cookies')
def check_cookies():
    status = _check_cookie_status_fast()
    return jsonify({
        'exists': status['exists'],
        'count': status['count'],
        'error': status['error'],
    })


@threads_bp.route('/api/verify-session')
def verify_session():
    fast = _check_cookie_status_fast()
    if not fast['exists'] or fast['count'] == 0:
        return jsonify({'ok': False, 'valid': False, 'error': 'No cookies found - import cookies first'})

    try:
        from seleniumbase import SB

        result = {'valid': False, 'error': None}

        def _run():
            try:
                with SB(uc=True, headless=True, xvfb=True) as sb:
                    sb.open(THREADS_HOME)
                    time.sleep(2)
                    for c in fast['cookies']:
                        try:
                            sb.driver.add_cookie({
                                'name': c.get('name', ''),
                                'value': c.get('value', ''),
                                'domain': c.get('domain', '.threads.com'),
                            })
                        except Exception:
                            pass
                    sb.driver.refresh()
                    time.sleep(4)
                    cur_url = sb.driver.current_url
                    if 'login' in cur_url:
                        result['valid'] = False
                        result['error'] = 'Session expired - please re-import fresh cookies'
                    else:
                        result['valid'] = True
            except Exception as e:
                result['error'] = str(e)

        t = threading.Thread(target=_run)
        t.start()
        t.join(timeout=35)
        return jsonify({'ok': True, 'valid': result['valid'], 'error': result['error']})
    except ImportError:
        return jsonify({
            'ok': False,
            'valid': False,
            'error': 'SeleniumBase unavailable - cannot verify session',
        })


def _check_cookie_status_fast():
    if not os.path.exists(COOKIE_FILE):
        return {'exists': False, 'count': 0, 'cookies': [], 'error': None}
    try:
        cookies = load_cookies_pickle(COOKIE_FILE)
        if not isinstance(cookies, list) or len(cookies) == 0:
            return {'exists': True, 'count': 0, 'cookies': [], 'error': 'Cookie file empty or corrupt'}
        if not cookies_have_any_domain(cookies, list(THREADS_COOKIE_DOMAINS)):
            return {
                'exists': True,
                'count': len(cookies),
                'cookies': cookies,
                'error': 'Cookie file has no Threads domain cookies',
            }
        return {'exists': True, 'count': len(cookies), 'cookies': cookies, 'error': None}
    except Exception as e:
        return {'exists': True, 'count': 0, 'cookies': [], 'error': f'Cannot read cookie file: {e}'}


@threads_bp.route('/api/investigations')
def get_investigations():
    import sqlite3

    try:
        con = sqlite3.connect(DB_FILE)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute(
            """
            SELECT
                p.id, p.profile_url, p.owner_name, p.is_locked, p.scraped_at,
                (SELECT COUNT(*) FROM text_posts WHERE profile_id = p.id) AS post_count,
                (SELECT COUNT(DISTINCT commentor_id) FROM commentor_frequency
                 WHERE profile_id = p.id) AS interactor_count,
                (SELECT COUNT(*) FROM detected_faces df
                 LEFT JOIN photo_posts pp ON pp.id = df.photo_post_id
                 LEFT JOIN text_posts tp ON tp.id = df.text_post_id
                 WHERE pp.profile_id = p.id OR tp.profile_id = p.id) AS face_count
            FROM profiles p
            ORDER BY p.id DESC
            """
        )
        rows = cur.fetchall()
        con.close()
        return jsonify({
            'ok': True,
            'records': [
                {
                    'id': r['id'],
                    'name': r['owner_name'] or 'Unknown',
                    'url': r['profile_url'],
                    'is_locked': bool(r['is_locked']),
                    'scraped_at': r['scraped_at'] or '',
                    'post_count': r['post_count'] or 0,
                    'interactor_count': r['interactor_count'] or 0,
                    'face_count': r['face_count'] or 0,
                }
                for r in rows
            ],
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@threads_bp.route('/api/investigations/<int:profile_id>', methods=['DELETE'])
def delete_investigation(profile_id):
    import sqlite3

    if not profile_id:
        return jsonify({'ok': False, 'error': 'profile_id required'}), 400

    try:
        con = sqlite3.connect(DB_FILE)
        cur = con.cursor()

        cur.execute(
            """
            SELECT df.face_image_path
            FROM detected_faces df
            LEFT JOIN photo_posts pp ON pp.id = df.photo_post_id
            LEFT JOIN text_posts tp ON tp.id = df.text_post_id
            WHERE (pp.profile_id = ? OR tp.profile_id = ?)
              AND df.face_image_path IS NOT NULL
            """,
            (profile_id, profile_id),
        )
        face_paths = [row[0] for row in cur.fetchall()]

        cur.execute(
            """
            DELETE FROM detected_faces
            WHERE photo_post_id IN (SELECT id FROM photo_posts WHERE profile_id = ?)
               OR text_post_id IN (SELECT id FROM text_posts WHERE profile_id = ?)
            """,
            (profile_id, profile_id),
        )

        cur.execute(
            """
            DELETE FROM top7_profile_fields
            WHERE top7_profile_id IN (
                SELECT id FROM top7_profiles WHERE profile_id = ?
            )
            """,
            (profile_id,),
        )
        cur.execute('DELETE FROM top7_profiles WHERE profile_id = ?', (profile_id,))
        cur.execute('DELETE FROM commentor_frequency WHERE profile_id = ?', (profile_id,))

        cur.execute(
            """
            DELETE FROM thread_likes
            WHERE post_id IN (SELECT id FROM text_posts WHERE profile_id = ?)
            """,
            (profile_id,),
        )
        cur.execute(
            """
            DELETE FROM thread_reposts
            WHERE post_id IN (SELECT id FROM text_posts WHERE profile_id = ?)
            """,
            (profile_id,),
        )
        cur.execute(
            """
            DELETE FROM thread_replies
            WHERE post_id IN (SELECT id FROM text_posts WHERE profile_id = ?)
            """,
            (profile_id,),
        )
        cur.execute(
            """
            DELETE FROM photo_comments
            WHERE photo_post_id IN (SELECT id FROM photo_posts WHERE profile_id = ?)
            """,
            (profile_id,),
        )
        cur.execute(
            """
            DELETE FROM reel_comments
            WHERE reel_post_id IN (SELECT id FROM reel_posts WHERE profile_id = ?)
            """,
            (profile_id,),
        )
        cur.execute(
            """
            DELETE FROM text_comments
            WHERE text_post_id IN (SELECT id FROM text_posts WHERE profile_id = ?)
            """,
            (profile_id,),
        )

        cur.execute('DELETE FROM photo_posts WHERE profile_id = ?', (profile_id,))
        cur.execute('DELETE FROM reel_posts WHERE profile_id = ?', (profile_id,))
        cur.execute('DELETE FROM text_posts WHERE profile_id = ?', (profile_id,))
        cur.execute('DELETE FROM profile_fields WHERE profile_id = ?', (profile_id,))
        cur.execute('DELETE FROM profiles WHERE id = ?', (profile_id,))

        cur.execute(
            """
            DELETE FROM commentors
            WHERE id NOT IN (SELECT commentor_id FROM photo_comments)
              AND id NOT IN (SELECT commentor_id FROM reel_comments)
              AND id NOT IN (SELECT commentor_id FROM text_comments)
              AND id NOT IN (SELECT commentor_id FROM thread_likes)
              AND id NOT IN (SELECT commentor_id FROM thread_reposts)
              AND id NOT IN (SELECT commentor_id FROM thread_replies)
            """
        )

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


@threads_bp.route('/api/start-pipeline', methods=['POST'])
def start_pipeline():
    if pipeline_state['running']:
        return jsonify({'ok': False, 'error': 'Pipeline already running'}), 409

    data = request.get_json(silent=True) or {}
    profile_url = data.get('profile_url', '').strip()
    depth = data.get('depth', 'light').strip().lower()
    if not profile_url:
        return jsonify({'ok': False, 'error': 'profile_url required'}), 400

    try:
        profile_url = normalize_threads_target(profile_url)
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400

    if depth not in DEPTH_LIMITS:
        depth = 'light'

    status = _check_cookie_status_fast()
    if not status['exists'] or status['count'] == 0:
        return jsonify({'ok': False, 'error': 'Cookie file not found - import cookies first'}), 400

    reset_pipeline(pipeline_state, PIPELINE_STEPS, profile_url=profile_url, depth=depth)
    pipeline_state['running'] = True
    pipeline_state['started_at'] = datetime.now().isoformat()
    threading.Thread(target=_run_pipeline, args=(profile_url, depth), daemon=True).start()
    return jsonify({'ok': True, 'message': 'Pipeline started'})


@threads_bp.route('/api/pipeline-status')
def pipeline_status():
    return jsonify({
        'ok': True,
        'running': pipeline_state['running'],
        'profile_url': pipeline_state['profile_url'],
        'depth': pipeline_state['depth'],
        'steps': pipeline_state['steps'],
        'error': pipeline_state['error'],
        'profile_id': pipeline_state['profile_id'],
        'started_at': pipeline_state['started_at'],
        'finished_at': pipeline_state['finished_at'],
    })


def _run_pipeline(profile_url, depth):
    import multiprocessing
    import random

    limits = DEPTH_LIMITS[depth]
    posts_limit = limits['posts']

    def _staggered(delay_s, fn, kwargs):
        time.sleep(delay_s + random.uniform(0, 1.0))
        fn(**kwargs)

    try:
        set_step(pipeline_state, 'about', 'active')
        set_step(pipeline_state, 'posts', 'active')

        p1 = multiprocessing.Process(
            target=_staggered,
            args=(0, scrape_about, {'PROFILE_URL': profile_url}),
            name='scrape-about',
        )
        p2 = multiprocessing.Process(
            target=_staggered,
            args=(2, scrape_posts, {'PROFILE_URL': profile_url, 'MAX_POSTS': posts_limit}),
            name='scrape-posts',
        )

        for p in [p1, p2]:
            p.start()

        for p, step_id in [(p1, 'about'), (p2, 'posts')]:
            p.join()
            if p.exitcode == 0:
                set_step(pipeline_state, step_id, 'done')
            else:
                set_step(pipeline_state, step_id, 'error')

        set_step(pipeline_state, 'db', 'active')
        try:
            import_all(
                about_json=os.path.join(BASE_DIR, 'threads_about.json'),
                posts_json=os.path.join(BASE_DIR, 'threads_posts.json'),
                db_file=DB_FILE,
                expected_profile_url=profile_url,
            )
            profile = get_profile_id(DB_FILE)
            if profile:
                pipeline_state['profile_id'] = profile['id']
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
            about_file = os.path.join(BASE_DIR, 'threads_about.json')
            if not os.path.exists(about_file):
                continue
            with open(about_file, encoding='utf-8') as f:
                data = json.load(f)
            sections = data.get('sections', {})
            con = sqlite3.connect(DB_FILE)
            cur = con.cursor()
            cur.execute(
                """
                SELECT id FROM top7_profiles
                WHERE profile_id = ? AND commentor_id = ?
                """,
                (profile_id, entry['commentor_id']),
            )
            row = cur.fetchone()
            if not row:
                con.close()
                continue
            t7id = row[0]
            cur.execute('DELETE FROM top7_profile_fields WHERE top7_profile_id = ?', (t7id,))
            for section, fields in sections.items():
                for field in fields:
                    cur.execute(
                        """
                        INSERT INTO top7_profile_fields
                            (top7_profile_id, section, field_type, label, value, sub_label)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            t7id,
                            section,
                            field.get('field_type'),
                            field.get('label'),
                            field.get('value'),
                            field.get('sub_label'),
                        ),
                    )
            con.commit()
            con.close()
        except Exception as e:
            print(f'  [TOP7] {url}: {e}')


def _step_error(step_id, exc):
    set_step(pipeline_state, step_id, 'error')
    print(f'[PIPELINE] {step_id} error: {exc}')


@threads_bp.route('/api/profile-summary/<int:profile_id>')
def api_profile_summary(profile_id):
    try:
        return jsonify({'ok': True, 'data': get_profile_summary(DB_FILE, profile_id)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@threads_bp.route('/api/all-interactors/<int:profile_id>')
def api_all_interactors(profile_id):
    import sqlite3

    try:
        con = sqlite3.connect(DB_FILE)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute(
            """
            SELECT
                co.id AS commentor_id,
                co.name,
                co.profile_url,
                cf.like_count,
                cf.repost_count,
                cf.reply_count,
                cf.photo_count,
                cf.reel_count,
                cf.text_count,
                cf.total_count
            FROM commentor_frequency cf
            JOIN commentors co ON co.id = cf.commentor_id
            WHERE cf.profile_id = ?
            ORDER BY cf.total_count DESC
            """,
            (profile_id,),
        )
        rows = [dict(r) for r in cur.fetchall()]
        con.close()
        return jsonify({'ok': True, 'data': rows})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@threads_bp.route('/api/top7/<int:profile_id>')
def api_top7(profile_id):
    try:
        return jsonify({'ok': True, 'data': get_top7(DB_FILE, profile_id)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@threads_bp.route('/api/graph-data/<int:profile_id>')
def api_graph_data(profile_id):
    try:
        return jsonify({'ok': True, 'data': get_graph_data(DB_FILE, profile_id)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@threads_bp.route('/api/cocomment-graph/<int:profile_id>')
def api_cocomment_graph(profile_id):
    try:
        return jsonify({'ok': True, 'data': get_cocomment_graph(DB_FILE, profile_id)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@threads_bp.route('/api/timeline/<int:profile_id>')
def api_timeline(profile_id):
    import sqlite3

    try:
        con = sqlite3.connect(DB_FILE)
        cur = con.cursor()
        cur.execute(
            """
            SELECT tp.date_text,
                   COUNT(DISTINCT tl.id) AS likes,
                   COUNT(DISTINCT trp.id) AS reposts,
                   COUNT(DISTINCT trr.id) AS replies
            FROM text_posts tp
            LEFT JOIN thread_likes tl ON tl.post_id = tp.id
            LEFT JOIN thread_reposts trp ON trp.post_id = tp.id
            LEFT JOIN thread_replies trr ON trr.post_id = tp.id
            WHERE tp.profile_id = ? AND tp.date_text IS NOT NULL
            GROUP BY tp.date_text
            ORDER BY tp.date_text
            """,
            (profile_id,),
        )
        rows = []
        for date_text, likes, reposts, replies in cur.fetchall():
            rows.append({
                'date': date_text,
                'likes': likes or 0,
                'reposts': reposts or 0,
                'replies': replies or 0,
                'photo': likes or 0,
                'reel': reposts or 0,
                'text': replies or 0,
                'total': (likes or 0) + (reposts or 0) + (replies or 0),
            })
        con.close()
        return jsonify({'ok': True, 'data': rows})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@threads_bp.route('/api/post-type-counts/<int:profile_id>')
def api_post_type_counts(profile_id):
    try:
        # Same shape as IG/FB: {posts:..., interactions:{photo,reel,text,total}}
        # Threads maps like→photo_comments, repost→reel_comments, reply→text_comments.
        return jsonify({'ok': True, 'data': get_post_type_counts(DB_FILE, profile_id)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@threads_bp.route('/api/face-clusters/<int:profile_id>')
def api_face_clusters(profile_id):
    import sqlite3

    try:
        con = sqlite3.connect(DB_FILE)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute(
            """
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
            """,
            (profile_id, profile_id),
        )
        rows = [dict(r) for r in cur.fetchall()]
        con.close()
        return jsonify({'ok': True, 'data': rows})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@threads_bp.route('/api/face-cluster/<int:cluster_id>/members')
def api_face_cluster_members(cluster_id):
    import sqlite3

    try:
        con = sqlite3.connect(DB_FILE)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute(
            """
            SELECT id, photo_post_id, text_post_id,
                   face_index, face_image_path, person_id
            FROM detected_faces
            WHERE person_id = ?
            ORDER BY id
            """,
            (cluster_id,),
        )
        rows = [dict(r) for r in cur.fetchall()]
        con.close()
        return jsonify({'ok': True, 'data': rows})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@threads_bp.route('/api/photo-posts/<int:profile_id>')
def api_photo_posts(profile_id):
    import sqlite3

    try:
        con = sqlite3.connect(DB_FILE)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute(
            """
            SELECT id, post_url AS photo_url, date_text, image_src, body AS caption
            FROM text_posts
            WHERE profile_id = ? AND COALESCE(media_type, 'text') IN ('image', 'video')
            ORDER BY id DESC
            """,
            (profile_id,),
        )
        rows = [dict(r) for r in cur.fetchall()]
        con.close()
        return jsonify({'ok': True, 'data': rows})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@threads_bp.route('/api/text-posts/<int:profile_id>')
def api_text_posts(profile_id):
    import sqlite3

    try:
        con = sqlite3.connect(DB_FILE)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute(
            """
            SELECT id, post_url, date_text, body, media_type, image_src
            FROM text_posts
            WHERE profile_id = ?
            ORDER BY id DESC
            """,
            (profile_id,),
        )
        rows = [dict(r) for r in cur.fetchall()]
        con.close()
        return jsonify({'ok': True, 'data': rows})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@threads_bp.route('/api/reel-posts/<int:profile_id>')
def api_reel_posts(profile_id):
    import sqlite3

    try:
        con = sqlite3.connect(DB_FILE)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute(
            """
            SELECT id, post_url AS reel_url, date_text, image_src, body AS caption
            FROM text_posts
            WHERE profile_id = ? AND COALESCE(media_type, 'text') = 'video'
            ORDER BY id DESC
            """,
            (profile_id,),
        )
        rows = [dict(r) for r in cur.fetchall()]
        con.close()
        return jsonify({'ok': True, 'data': rows})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@threads_bp.route('/logo')
def serve_logo():
    logo = os.path.join(BASE_DIR, 'icons', 'logo.jpeg')
    if os.path.exists(logo):
        return send_file(logo, mimetype='image/jpeg')
    import base64
    px = base64.b64decode('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7')
    return Response(px, mimetype='image/gif')


@threads_bp.route('/threat')
def serve_icon():
    logo = os.path.join(BASE_DIR, 'icons', 'search.png')
    if os.path.exists(logo):
        return send_file(logo, mimetype='image/jpeg')
    import base64
    px = base64.b64decode('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7')
    return Response(px, mimetype='image/gif')


@threads_bp.route('/user')
def serve_user():
    logo = os.path.join(BASE_DIR, 'icons', 'spy.png')
    if os.path.exists(logo):
        return send_file(logo, mimetype='image/jpeg')
    import base64
    px = base64.b64decode('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7')
    return Response(px, mimetype='image/gif')


@threads_bp.route('/face-image/<path:filepath>')
def face_image(filepath):
    try:
        full = safe_under(BASE_DIR, filepath)
    except ValueError:
        return '', 404
    if os.path.exists(full):
        return send_file(full)
    return '', 404
