from flask import Blueprint, jsonify, current_app
import time

obs_bp = Blueprint('observability', __name__)

_db = None
_log_queue = None


def init_observability(database, log_queue):
    global _db, _log_queue
    _db = database
    _log_queue = log_queue


@obs_bp.route('/health', methods=['GET'])
def health():
    # Basic health check: DB reachable and app running
    db_ok = False
    try:
        if _db is not None:
            conn = _db._get_conn()
            cur = conn.cursor()
            cur.execute('SELECT 1')
            _ = cur.fetchone()
            db_ok = True
    except Exception as e:
        # don't expose exception details in response, but log on server side
        try:
            current_app.logger.exception('Health check DB error')
        except Exception:
            pass
        db_ok = False

    status = 'ok' if db_ok else 'degraded'
    http_status = 200 if db_ok else 503
    return jsonify({'status': status}), http_status


@obs_bp.route('/metrics', methods=['GET'])
def metrics():
    # Return basic JSON metrics: queue length, receive rates
    rate_1min, rate_5min, total_received = (0, 0, 0)
    try:
        from web.api import get_current_rate
        rate_1min, rate_5min, total_received = get_current_rate()
    except Exception:
        try:
            current_app.logger.exception('Failed to read rates for metrics')
        except Exception:
            pass

    queue_len = None
    try:
        if _log_queue is not None:
            queue_len = _log_queue.qsize()
    except Exception:
        queue_len = None

    total_logs = None
    try:
        # Reuse storage info logic if available
        from web.api import _get_storage_info
        storage = _get_storage_info()
        total_logs = storage.get('total_logs')
    except Exception:
        try:
            if _db is not None:
                conn = _db._get_conn()
                cursor = conn.cursor()
                cursor.execute('SELECT COUNT(*) as count FROM syslogs')
                row = cursor.fetchone()
                total_logs = row['count'] if row and 'count' in row else row[0] if row else None
        except Exception:
            total_logs = None

    return jsonify({
        'queue_length': queue_len,
        'rate_1min': round(rate_1min, 2) if isinstance(rate_1min, (int, float)) else rate_1min,
        'rate_5min': round(rate_5min, 2) if isinstance(rate_5min, (int, float)) else rate_5min,
        'total_received_since_start': total_received,
        'total_logs': total_logs
    })
