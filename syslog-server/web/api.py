from flask import Blueprint, jsonify, request, render_template, Response
from database.db import Database
from config import Config
from syslog_server.vendor_detector import get_detector
import json
import time
import os
import threading
from datetime import datetime, timedelta
from collections import deque

api_bp = Blueprint('api', __name__)
db = None
log_queue = None

_rate_lock = threading.Lock()
_recent_counts = deque()
_total_received = 0

def init_api(database, queue):
    global db, log_queue
    db = database
    log_queue = queue
    _start_rate_monitor()

def record_log_received(count=1):
    global _total_received
    with _rate_lock:
        _total_received += count

def _start_rate_monitor():
    def monitor():
        while True:
            time.sleep(1)
            with _rate_lock:
                now = time.time()
                _recent_counts.append((now, _total_received))
                while _recent_counts and now - _recent_counts[0][0] > 300:
                    _recent_counts.popleft()
    t = threading.Thread(target=monitor, daemon=True)
    t.start()

def get_current_rate():
    with _rate_lock:
        if len(_recent_counts) < 2:
            return 0, 0, 0
        now = time.time()
        recent_1min = [(t, c) for t, c in _recent_counts if now - t <= 60]
        recent_5min = list(_recent_counts)
        if len(recent_1min) < 2:
            rate_1min = 0
        else:
            time_diff = recent_1min[-1][0] - recent_1min[0][0]
            count_diff = recent_1min[-1][1] - recent_1min[0][1]
            rate_1min = count_diff / time_diff if time_diff > 0 else 0
        if len(recent_5min) < 2:
            rate_5min = 0
        else:
            time_diff = recent_5min[-1][0] - recent_5min[0][0]
            count_diff = recent_5min[-1][1] - recent_5min[0][1]
            rate_5min = count_diff / time_diff if time_diff > 0 else 0
        return rate_1min, rate_5min, _total_received

@api_bp.route('/')
def index():
    return render_template('index.html',
                         facilities=Config.FACILITY_MAP,
                         severities=Config.SEVERITY_MAP,
                         severity_colors=Config.SEVERITY_COLORS)

@api_bp.route('/api/logs', methods=['GET'])
def get_logs():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    severity = request.args.get('severity', type=int)
    facility = request.args.get('facility', type=int)
    hostname = request.args.get('hostname')
    source_ip = request.args.get('source_ip')
    app_name = request.args.get('app_name')
    vendor = request.args.get('vendor')
    search = request.args.get('search')
    start_time = request.args.get('start_time')
    end_time = request.args.get('end_time')
    order = request.args.get('order', 'desc')

    result = db.get_logs(
        page=page,
        per_page=per_page,
        severity=severity,
        facility=facility,
        hostname=hostname,
        source_ip=source_ip,
        app_name=app_name,
        vendor=vendor,
        search=search,
        start_time=start_time,
        end_time=end_time,
        order=order
    )

    return jsonify(result)

@api_bp.route('/api/logs/<int:log_id>', methods=['GET'])
def get_log(log_id):
    log = db.get_log_by_id(log_id)
    if log:
        return jsonify(log)
    return jsonify({'error': 'Log not found'}), 404

@api_bp.route('/api/stats', methods=['GET'])
def get_stats():
    hours = request.args.get('hours', 24, type=int)
    stats = db.get_statistics(hours=hours)

    rate_1min, rate_5min, total_received = get_current_rate()
    stats['rate_1min'] = round(rate_1min, 2)
    stats['rate_5min'] = round(rate_5min, 2)
    stats['total_received_since_start'] = total_received

    storage_info = _get_storage_info()
    stats['storage'] = storage_info

    compliance = _check_compliance(stats, storage_info)
    stats['compliance'] = compliance

    return jsonify(stats)

def _get_storage_info():
    db_path = Config.DATABASE_PATH
    try:
        db_size = os.path.getsize(db_path)
    except OSError:
        db_size = 0

    total_logs = 0
    try:
        conn = db._get_conn()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) as count FROM syslogs')
        total_logs = cursor.fetchone()['count']
    except Exception:
        pass

    avg_log_size = db_size / total_logs if total_logs > 0 else 500

    try:
        statvfs = os.statvfs(os.path.dirname(db_path))
        total_space = statvfs.f_frsize * statvfs.f_blocks
        free_space = statvfs.f_frsize * statvfs.f_bavail
    except Exception:
        total_space = 0
        free_space = 0

    rate_1min, rate_5min, _ = get_current_rate()
    rate_per_day = rate_5min * 86400 if rate_5min > 0 else 0

    est_days_by_db = 0
    est_days_by_disk = 0
    max_days = Config.MAX_LOG_AGE_DAYS

    if rate_per_day > 0 and avg_log_size > 0:
        if total_logs > 0:
            current_days_data = (db_size / (total_logs / max_days)) if max_days > 0 else 0
        est_days_by_db = (free_space / avg_log_size) / rate_per_day if rate_per_day > 0 else 0
        est_days_by_disk = (free_space / avg_log_size) / rate_per_day if rate_per_day > 0 else 0
        est_days_by_db = min(est_days_by_db, max_days)

    daily_growth_bytes = rate_per_day * avg_log_size

    return {
        'db_size_bytes': db_size,
        'db_size_mb': round(db_size / 1024 / 1024, 2),
        'total_logs': total_logs,
        'avg_log_size_bytes': round(avg_log_size, 1),
        'free_space_bytes': free_space,
        'free_space_gb': round(free_space / 1024 / 1024 / 1024, 2),
        'total_space_bytes': total_space,
        'total_space_gb': round(total_space / 1024 / 1024 / 1024, 2),
        'rate_per_day': round(rate_per_day, 0),
        'daily_growth_mb': round(daily_growth_bytes / 1024 / 1024, 2),
        'estimated_days_by_space': round(est_days_by_disk, 1),
        'estimated_days_by_config': max_days,
        'max_log_age_days': max_days
    }

def _check_compliance(stats, storage_info):
    checks = []
    overall_pass = True

    retention_days = storage_info.get('estimated_days_by_space', 0)
    config_retention = storage_info.get('max_log_age_days', 0)
    min_retention = min(retention_days, config_retention)
    retention_pass = min_retention >= 180
    checks.append({
        'id': 'retention',
        'name': '日志留存时间',
        'requirement': '日志留存不少于6个月（180天）',
        'current': f'预估可留存 {round(min_retention, 1)} 天（配置保留 {config_retention} 天）',
        'pass': retention_pass
    })
    if not retention_pass:
        overall_pass = False

    required_fields = ['id', 'timestamp', 'severity', 'facility', 'hostname', 'source_ip', 'app_name', 'message', 'raw_message', 'received_at']
    field_check_pass = True
    sample_log = stats.get('severity_stats', {})
    if sample_log:
        field_check_pass = True
    checks.append({
        'id': 'log_fields',
        'name': '日志字段完整性',
        'requirement': '记录事件时间、类型、主体、结果等',
        'current': '包含时间、级别、设施、主机、IP、应用、消息等字段',
        'pass': True
    })

    checks.append({
        'id': 'time_sync',
        'name': '时间同步',
        'requirement': '系统时间准确，日志时间戳可信',
        'current': '使用系统本地时间',
        'pass': True,
        'warn': True
    })

    checks.append({
        'id': 'backup',
        'name': '日志备份',
        'requirement': '审计记录定期备份，防止意外丢失',
        'current': '当前未配置自动备份机制',
        'pass': False
    })
    overall_pass = False

    checks.append({
        'id': 'integrity',
        'name': '日志完整性保护',
        'requirement': '防止日志被未授权删除或修改',
        'current': '数据库文件可被修改，未启用完整性校验',
        'pass': False
    })
    overall_pass = False

    checks.append({
        'id': 'access_control',
        'name': '访问控制',
        'requirement': '仅授权人员可访问和操作日志',
        'current': 'Web界面无身份认证',
        'pass': False
    })
    overall_pass = False

    checks.append({
        'id': 'alert',
        'name': '异常告警',
        'requirement': '对重要安全事件进行告警',
        'current': '未配置安全事件告警规则',
        'pass': False
    })
    overall_pass = False

    return {
        'level': '等保三级',
        'overall_pass': overall_pass,
        'checks': checks,
        'pass_count': sum(1 for c in checks if c['pass']),
        'total_count': len(checks)
    }

@api_bp.route('/api/recent', methods=['GET'])
def get_recent():
    limit = request.args.get('limit', 100, type=int)
    logs = db.get_recent_logs(limit=limit)
    return jsonify(logs)

@api_bp.route('/api/values/<column>', methods=['GET'])
def get_values(column):
    values = db.get_distinct_values(column)
    return jsonify(values)

@api_bp.route('/api/logs', methods=['DELETE'])
def delete_logs():
    days = request.args.get('days', type=int)
    if days is not None:
        deleted = db.cleanup_old_logs(days=days)
        return jsonify({'deleted': deleted, 'method': 'cleanup'})
    else:
        db.clear_all_logs()
        return jsonify({'deleted': 'all', 'method': 'clear'})

@api_bp.route('/api/stream')
def stream():
    def event_stream():
        last_id = 0
        heartbeat_count = 0
        while True:
            try:
                logs = db.get_recent_logs(limit=50)
                new_logs = [log for log in logs if log['id'] > last_id]
                if new_logs:
                    last_id = new_logs[0]['id']
                    for log in reversed(new_logs):
                        yield f"data: {json.dumps(log)}\n\n"
                else:
                    heartbeat_count += 1
                    if heartbeat_count >= 5:
                        yield ":heartbeat\n\n"
                        heartbeat_count = 0
                time.sleep(1)
            except GeneratorExit:
                break
            except (BrokenPipeError, ConnectionResetError, OSError):
                break
            except Exception:
                time.sleep(1)

    response = Response(
        event_stream(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
            'Access-Control-Allow-Origin': '*'
        }
    )
    return response

@api_bp.route('/api/send-test', methods=['POST'])
def send_test():
    data = request.get_json()
    count = data.get('count', 1) if data else 1
    
    import socket
    import random
    
    test_messages = [
        "System started successfully",
        "User admin logged in from 192.168.1.100",
        "Disk space warning: /dev/sda1 is at 85% capacity",
        "Connection timeout to database server",
        "Configuration file reloaded",
        "Memory usage is high: 90% used",
        "Security alert: failed login attempt from 10.0.0.5",
        "Backup completed successfully",
        "Service restarted due to memory leak",
        "New version deployed successfully"
    ]
    
    test_hosts = ["server-01", "server-02", "web-server", "db-server", "app-server"]
    test_apps = ["sshd", "kernel", "nginx", "mysqld", "systemd", "cron"]
    
    sent = 0
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    for i in range(count):
        severity = random.randint(0, 7)
        facility = random.randint(0, 23)
        priority = (facility << 3) | severity
        host = random.choice(test_hosts)
        app = random.choice(test_apps)
        msg = random.choice(test_messages)
        timestamp = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
        
        syslog_msg = f"<{priority}>1 {timestamp} {host} {app} {random.randint(1000,9999)} - {msg}"
        
        try:
            sock.sendto(syslog_msg.encode(), ('127.0.0.1', Config.SYSLOG_UDP_PORT))
            sent += 1
        except Exception as e:
            print(f"Error sending test message: {e}")
    
    sock.close()
    
    return jsonify({'sent': sent})

@api_bp.route('/api/config', methods=['GET'])
def get_config():
    detector = get_detector()
    vendors = detector.get_all_vendors()
    vendor_list = {k: {'name': v['name'], 'icon': v['icon'], 'color': v['color']} for k, v in vendors.items()}
    return jsonify({
        'udp_port': Config.SYSLOG_UDP_PORT,
        'tcp_port': Config.SYSLOG_TCP_PORT,
        'web_port': Config.WEB_PORT,
        'facilities': Config.FACILITY_MAP,
        'severities': Config.SEVERITY_MAP,
        'severity_colors': Config.SEVERITY_COLORS,
        'vendors': vendor_list
    })
