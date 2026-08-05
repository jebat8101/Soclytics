"""Shared Flask routes for PDF / JSON investigation report downloads."""
from __future__ import annotations

import os
import traceback

from flask import jsonify, send_file


def register_report_routes(bp, db_file: str, platform: str) -> None:
    """
    Attach /reports/pdf/<id> and /reports/json/<id> to a platform blueprint.

    Downloads are generated on demand under app/reports/.
    """

    @bp.route('/reports/pdf/<int:profile_id>')
    def serve_pdf_report(profile_id):
        try:
            from core.report import generate_report
            path = generate_report(profile_id, db_file=db_file, platform=platform)
            return send_file(
                path,
                mimetype='application/pdf',
                as_attachment=True,
                download_name=os.path.basename(path),
            )
        except ValueError as e:
            return jsonify({'ok': False, 'error': str(e)}), 404
        except ImportError as e:
            return jsonify({
                'ok': False,
                'error': f'Report deps missing — pip install reportlab matplotlib ({e})',
            }), 500
        except Exception as e:
            traceback.print_exc()
            return jsonify({'ok': False, 'error': str(e)}), 500

    @bp.route('/reports/json/<int:profile_id>')
    def serve_json_report(profile_id):
        try:
            from core.report import generate_json_report
            path = generate_json_report(profile_id, db_file=db_file, platform=platform)
            return send_file(
                path,
                mimetype='application/json',
                as_attachment=True,
                download_name=os.path.basename(path),
            )
        except ValueError as e:
            return jsonify({'ok': False, 'error': str(e)}), 404
        except Exception as e:
            traceback.print_exc()
            return jsonify({'ok': False, 'error': str(e)}), 500
