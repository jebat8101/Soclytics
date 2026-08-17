"""Telegram mini-app Flask blueprint — MTProto + public t.me/s fallback."""
import os
import threading
import traceback
from datetime import datetime

from flask import (
    Blueprint, render_template, request, jsonify, redirect, url_for,
    send_file, Response,
)

from core.paths import safe_under
from core.urls import normalize_telegram_target, extract_telegram_username
from platforms.telegram.constants import (
    BASE_DIR, DB_FILE, ICONS_DIR, FACE_DIR, MEDIA_DIR,
    ABOUT_OUT, PHOTOS_OUT, REELS_OUT, POSTS_OUT,
    DEPTH_LIMITS, PIPELINE_STEPS,
)
from platforms.telegram.db import import_all, compute_frequency, extract_top7
from platforms.telegram.collector import collect, check_session_valid
from core.engagement_metrics import get_activity_metrics
from platforms.telegram.text_metrics import (
    get_word_stats,
    search_word,
    word_frequencies,
    render_word_cloud_png,
)

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
os.makedirs(MEDIA_DIR, exist_ok=True)

pipeline_state = make_pipeline_state(PIPELINE_STEPS)

telegram_bp = Blueprint('telegram', __name__, url_prefix='/telegram')
register_report_routes(telegram_bp, DB_FILE, 'telegram')


@telegram_bp.route('/')
def home():
    session_status = _session_status()
    return render_template('telegram/index.html', session_status=session_status)


@telegram_bp.route('/analysis')
def analysis():
    profile_id = request.args.get('id', type=int)
    if not profile_id:
        return redirect(url_for('telegram.home'))
    profile = get_profile_summary(DB_FILE, profile_id)
    if not profile:
        return redirect(url_for('telegram.home'))
    return render_template('telegram/analysis.html', profile=profile, profile_id=profile_id)


def _session_status():
    ok, note = check_session_valid()
    msg = note or 'Public preview available'
    mode = 'mtproto' if msg.startswith('MTProto session ready') else 'public'
    return {
        'ready': True,
        'ok': ok,
        'mode': mode,
        'message': msg,
    }


@telegram_bp.route('/api/check-session')
def check_session():
    status = _session_status()
    return jsonify({
        'ok': True,
        'ready': status['ready'],
        'mode': status['mode'],
        'message': status['message'],
    })


@telegram_bp.route('/api/verify-session')
def verify_session():
    status = _session_status()
    return jsonify({
        'ok': True,
        'valid': status['ready'],
        'mode': status['mode'],
        'error': None if status['ready'] else status['message'],
        'message': status['message'],
    })


@telegram_bp.route('/api/check-cookies')
def check_cookies_compat():
    """Compat shim — Telegram never uses cookies; UI can call this safely."""
    status = _session_status()
    return jsonify({
        'exists': True,
        'count': 0,
        'optional': True,
        'mode': status['mode'],
        'message': status['message'],
        'error': None,
    })


@telegram_bp.route('/api/import-cookies', methods=['POST'])
def import_cookies():
    return jsonify({
        'ok': False,
        'error': 'Telegram uses MTProto, not cookies — set TG_API_ID / TG_API_HASH '
                 'and run: python3 scripts/telegram-login.py',
    }), 400


@telegram_bp.route('/api/investigations')
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


@telegram_bp.route('/api/investigations/<int:profile_id>', methods=['DELETE'])
def delete_investigation(profile_id):
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
            WHERE photo_post_id IN (SELECT id FROM photo_posts WHERE profile_id = ?)
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
            WHERE top7_profile_id IN (SELECT id FROM top7_profiles WHERE profile_id = ?)
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


@telegram_bp.route('/api/start-pipeline', methods=['POST'])
def start_pipeline():
    if pipeline_state['running']:
        return jsonify({'ok': False, 'error': 'Pipeline already running'}), 409

    data = request.get_json(silent=True) or {}
    profile_url = (data.get('profile_url') or '').strip()
    depth = (data.get('depth') or 'light').strip().lower()

    if not profile_url:
        return jsonify({'ok': False, 'error': 'profile_url required'}), 400
    if depth not in DEPTH_LIMITS:
        depth = 'light'

    try:
        profile_url = normalize_telegram_target(profile_url)
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400

    if not extract_telegram_username(profile_url):
        return jsonify({
            'ok': False,
            'error': 'Telegram invite links have no public username — use t.me/<channel>',
        }), 400

    reset_pipeline(pipeline_state, PIPELINE_STEPS, profile_url=profile_url, depth=depth)
    pipeline_state['running'] = True
    pipeline_state['started_at'] = datetime.now().isoformat()

    threading.Thread(target=_run_pipeline, args=(profile_url, depth), daemon=True).start()
    return jsonify({'ok': True, 'message': 'Telegram pipeline started'})


@telegram_bp.route('/api/pipeline-status')
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
    limits = DEPTH_LIMITS[depth]
    posts_limit = limits['posts']
    reels_limit = limits['reels']
    photos_limit = limits['photos']

    try:
        for step_id in ('about', 'photos', 'reels', 'posts'):
            set_step(pipeline_state, step_id, 'active')

        try:
            result = collect(
                profile_url,
                max_posts=posts_limit,
                max_photos=photos_limit,
                max_reels=reels_limit,
            )
            for step_id in ('about', 'photos', 'reels', 'posts'):
                set_step(pipeline_state, step_id, 'done')
            print(f"[TELEGRAM] collect mode={result.get('mode')} counts={result.get('counts')}")
        except Exception as e:
            for step_id in ('about', 'photos', 'reels', 'posts'):
                set_step(pipeline_state, step_id, 'error')
            finish_pipeline(pipeline_state, error=str(e))
            return

        set_step(pipeline_state, 'db', 'active')
        try:
            import_all(
                about_json=ABOUT_OUT,
                photos_json=PHOTOS_OUT,
                reels_json=REELS_OUT,
                posts_json=POSTS_OUT,
                db_file=DB_FILE,
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
            extract_top7(DB_FILE, profile_id)
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


def _step_error(step_id, exc):
    set_step(pipeline_state, step_id, 'error')
    print(f'[PIPELINE] {step_id} error: {exc}')


@telegram_bp.route('/api/profile-summary/<int:profile_id>')
def api_profile_summary(profile_id):
    try:
        return jsonify({'ok': True, 'data': get_profile_summary(DB_FILE, profile_id)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@telegram_bp.route('/api/all-interactors/<int:profile_id>')
def api_all_interactors(profile_id):
    try:
        return jsonify({'ok': True, 'data': get_all_interactors(DB_FILE, profile_id)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@telegram_bp.route('/api/top7/<int:profile_id>')
def api_top7(profile_id):
    try:
        return jsonify({'ok': True, 'data': get_top7(DB_FILE, profile_id)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@telegram_bp.route('/api/graph-data/<int:profile_id>')
def api_graph_data(profile_id):
    try:
        return jsonify({'ok': True, 'data': get_graph_data(DB_FILE, profile_id)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@telegram_bp.route('/api/cocomment-graph/<int:profile_id>')
def api_cocomment_graph(profile_id):
    try:
        return jsonify({'ok': True, 'data': get_cocomment_graph(DB_FILE, profile_id)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@telegram_bp.route('/api/timeline/<int:profile_id>')
def api_timeline(profile_id):
    try:
        return jsonify({'ok': True, 'data': get_interaction_timeline(DB_FILE, profile_id)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@telegram_bp.route('/api/activity-metrics/<int:profile_id>')
def api_activity_metrics(profile_id):
    """ConvoMetrics-style message activity (day / weekday / hour)."""
    try:
        return jsonify({'ok': True, 'data': get_activity_metrics(DB_FILE, profile_id)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@telegram_bp.route('/api/word-stats/<int:profile_id>')
def api_word_stats(profile_id):
    """Top words + cloud tokens, optional sender filter."""
    try:
        sender = (request.args.get('sender') or 'All').strip() or 'All'
        limit = request.args.get('limit', 40, type=int) or 40
        limit = max(5, min(limit, 100))
        return jsonify({
            'ok': True,
            'data': get_word_stats(DB_FILE, profile_id, sender=sender, limit=limit),
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@telegram_bp.route('/api/word-cloud/<int:profile_id>')
def api_word_cloud(profile_id):
    """PNG visual word cloud (ConvoMetrics-style)."""
    try:
        sender = (request.args.get('sender') or 'All').strip() or 'All'
        freqs = word_frequencies(DB_FILE, profile_id, sender=sender, limit=120)
        png = render_word_cloud_png(freqs)
        if not png:
            return jsonify({'ok': False, 'error': 'No textual data for word cloud'}), 404
        return Response(png, mimetype='image/png', headers={
            'Cache-Control': 'no-store',
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@telegram_bp.route('/api/word-search/<int:profile_id>')
def api_word_search(profile_id):
    """Who said a word, and when."""
    try:
        term = (request.args.get('q') or request.args.get('term') or '').strip()
        if not term:
            return jsonify({'ok': False, 'error': 'Missing q parameter'}), 400
        return jsonify({'ok': True, 'data': search_word(DB_FILE, profile_id, term)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@telegram_bp.route('/api/post-type-counts/<int:profile_id>')
def api_post_type_counts(profile_id):
    try:
        return jsonify({'ok': True, 'data': get_post_type_counts(DB_FILE, profile_id)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@telegram_bp.route('/api/face-clusters/<int:profile_id>')
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


@telegram_bp.route('/api/face-cluster/<int:cluster_id>/members')
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


@telegram_bp.route('/api/photo-posts/<int:profile_id>')
def api_photo_posts(profile_id):
    import sqlite3
    try:
        con = sqlite3.connect(DB_FILE)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute("""
            SELECT pp.id, pp.photo_url, pp.image_src, pp.caption, pp.date_text,
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


@telegram_bp.route('/api/text-posts/<int:profile_id>')
def api_text_posts(profile_id):
    import sqlite3
    try:
        con = sqlite3.connect(DB_FILE)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute("""
            SELECT tp.id, tp.post_url, tp.screenshot_path, tp.date_text,
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


@telegram_bp.route('/api/reel-posts/<int:profile_id>')
def api_reel_posts(profile_id):
    import sqlite3
    try:
        con = sqlite3.connect(DB_FILE)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute("""
            SELECT rp.id, rp.reel_url, rp.scraped_at,
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


@telegram_bp.route('/logo')
def serve_logo():
    logo = os.path.join(BASE_DIR, 'icons', 'logo.png')
    if os.path.exists(logo):
        return send_file(logo, mimetype='image/png')
    import base64
    px = base64.b64decode('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7')
    return Response(px, mimetype='image/gif')


@telegram_bp.route('/threat')
def serve_icon():
    logo = os.path.join(BASE_DIR, 'icons', 'search1.png')
    if os.path.exists(logo):
        return send_file(logo, mimetype='image/png')
    import base64
    px = base64.b64decode('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7')
    return Response(px, mimetype='image/gif')


@telegram_bp.route('/user')
def serve_user():
    logo = os.path.join(BASE_DIR, 'icons', 'spy.png')
    if os.path.exists(logo):
        return send_file(logo, mimetype='image/jpeg')
    import base64
    px = base64.b64decode('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7')
    return Response(px, mimetype='image/gif')


@telegram_bp.route('/face-image/<path:filepath>')
def face_image(filepath):
    try:
        full = safe_under(BASE_DIR, filepath)
    except ValueError:
        return '', 404
    if os.path.exists(full):
        return send_file(full)
    return '', 404


@telegram_bp.route('/screenshot/<path:filepath>')
def serve_screenshot(filepath):
    try:
        full = safe_under(BASE_DIR, filepath)
    except ValueError:
        return '', 404
    if os.path.exists(full):
        return send_file(full)
    return '', 404


@telegram_bp.route('/media/<path:filepath>')
def serve_media(filepath):
    """Serve downloaded Telegram media under telegram_media/."""
    try:
        full = safe_under(MEDIA_DIR, filepath)
    except ValueError:
        return '', 404
    if os.path.exists(full):
        return send_file(full)
    return '', 404
