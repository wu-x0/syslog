from flask import Blueprint, jsonify, request, render_template, Response, session, redirect, url_for, abort
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

def _write_system_log(level, category, message, details=None):
    try:
        if db and hasattr(db, 'add_system_log'):
            db.add_system_log(level, category, message, details,
                              source_ip=request.remote_addr if request else None)
    except Exception:
        pass

def login_required(f):
    def wrapper(*args, **kwargs):
        if not Config.AUTH_ENABLED:
            return f(*args, **kwargs)
        if 'logged_in' not in session or not session['logged_in']:
            return redirect(url_for('api.login'))
        
        # 检查 session 超时（固定过期），timeout <= 0 表示永不过期
        # 用户需求：长时间未操作就退出，从登录时间算起
        timeout = int(db.get_setting('session_timeout', 3600)) if db else 3600
        login_time = session.get('login_time', 0)
        if timeout > 0 and time.time() - login_time > timeout:
            _write_system_log('info', 'auth', f'用户 {session.get("username", "unknown")} 因会话超时被登出', f'登录时长: {int(time.time() - login_time)}秒, 超时设置: {timeout}秒')
            session.clear()
            return redirect(url_for('api.login'))
        
        # 强制修改密码
        if session.get('force_password_change'):
            return redirect(url_for('api.change_password'))
        
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

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
@login_required
def index():
    return render_template('index.html',
                         facilities=Config.FACILITY_MAP,
                         severities=Config.SEVERITY_MAP,
                         severity_colors=Config.SEVERITY_COLORS)

@api_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        client_ip = request.remote_addr
        
        # 检查IP是否被封禁
        ban_duration = int(db.get_setting('login_ban_duration', 300)) if db else 300
        max_attempts = int(db.get_setting('login_max_attempts', 5)) if db else 5
        
        stored_password = db.get_setting('admin_password', Config.ADMIN_PASSWORD) if db else Config.ADMIN_PASSWORD
        is_default_password = (stored_password == Config.ADMIN_PASSWORD)

        if db and hasattr(db, 'is_ip_banned') and db.is_ip_banned(client_ip, ban_duration):
            return render_template('login.html', error=f'您的IP ({client_ip}) 因多次登录失败已被临时封禁，请稍后再试', show_default_credentials=is_default_password)
        
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username == Config.ADMIN_USERNAME and password == stored_password:
            # 登录成功，清除失败记录
            if db and hasattr(db, 'clear_login_failures'):
                db.clear_login_failures(client_ip)
            session['logged_in'] = True
            session['username'] = username
            session['login_time'] = time.time()
            _write_system_log('info', 'auth', f'用户 {username} 登录成功', f'登录IP: {client_ip}')
            # 首次登录（仍使用默认密码），强制修改密码
            if is_default_password:
                session['force_password_change'] = True
                _write_system_log('warning', 'auth', f'用户 {username} 使用默认密码登录，强制修改密码', f'登录IP: {client_ip}')
                return redirect(url_for('api.change_password'))
            return redirect(url_for('api.index'))
        else:
            # 登录失败，记录失败次数
            _write_system_log('warning', 'auth', f'用户 {username} 登录失败', f'登录IP: {client_ip}')
            if db and hasattr(db, 'record_login_failure'):
                db.record_login_failure(client_ip)
                attempts = db.get_login_failures(client_ip, ban_duration)
                if attempts >= max_attempts:
                    _write_system_log('error', 'auth', f'IP {client_ip} 因连续登录失败被封禁', f'失败次数: {attempts}, 封禁时长: {ban_duration}秒')
                    return render_template('login.html', error=f'您的IP ({client_ip}) 因连续{max_attempts}次登录失败已被封禁{ban_duration}秒', show_default_credentials=is_default_password)
            return render_template('login.html', error='用户名或密码错误', show_default_credentials=is_default_password)
    stored_password = db.get_setting('admin_password', Config.ADMIN_PASSWORD) if db else Config.ADMIN_PASSWORD
    is_default_password = (stored_password == Config.ADMIN_PASSWORD)
    return render_template('login.html', show_default_credentials=is_default_password)

@api_bp.route('/change-password', methods=['GET', 'POST'])
def change_password():
    if 'logged_in' not in session or not session['logged_in']:
        return redirect(url_for('api.login'))
    if not session.get('force_password_change'):
        return redirect(url_for('api.index'))
    if request.method == 'POST':
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        if not new_password or not confirm_password:
            return render_template('change_password.html', error='请输入新密码')
        if new_password != confirm_password:
            return render_template('change_password.html', error='两次输入的密码不一致')
        if new_password == Config.ADMIN_PASSWORD:
            return render_template('change_password.html', error='新密码不能与默认密码相同')
        if db:
            db.set_setting('admin_password', new_password)
        username = session.get('username', 'unknown')
        _write_system_log('info', 'config', f'用户 {username} 修改了管理员密码', None)
        session.pop('force_password_change', None)
        return redirect(url_for('api.index'))
    return render_template('change_password.html')

@api_bp.route('/logout')
@login_required
def logout():
    username = session.get('username', 'unknown')
    client_ip = request.remote_addr
    _write_system_log('info', 'auth', f'用户 {username} 退出登录', f'退出IP: {client_ip}')
    session.clear()
    return redirect(url_for('api.login'))

@api_bp.route('/api/restart', methods=['POST'])
@login_required
def restart_server():
    username = session.get('username', 'unknown')
    _write_system_log('info', 'system', '用户发起服务重启', f'操作账号: {username}')

    def do_restart():
        time.sleep(2)
        os.execv(sys.executable, [sys.executable] + sys.argv)

    t = threading.Thread(target=do_restart, daemon=True)
    t.start()
    return jsonify({'success': True, 'message': '服务正在重启，请稍后刷新页面'})

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

@api_bp.route('/api/system-logs', methods=['GET'])
@login_required
def get_system_logs_api():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    level = request.args.get('level')
    category = request.args.get('category')
    search = request.args.get('search')
    order = request.args.get('order', 'desc')

    result = db.get_system_logs(
        page=page,
        per_page=per_page,
        level=level,
        category=category,
        search=search,
        order=order
    )
    return jsonify(result)

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

    if avg_log_size > 0 and free_space > 0:
        if rate_per_day > 0:
            est_days_by_disk = (free_space / avg_log_size) / rate_per_day
            est_days_by_db = min(est_days_by_disk, max_days)
        elif total_logs > 0:
            est_days_by_disk = (free_space / db_size) * max_days
            est_days_by_db = min(est_days_by_disk, max_days)
        else:
            est_days_by_disk = (free_space / avg_log_size) / 10000
            est_days_by_db = min(est_days_by_disk, max_days)

    daily_growth_bytes = rate_per_day * avg_log_size if rate_per_day > 0 else avg_log_size * 10000

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

    ntp_status = _check_ntp_sync()
    checks.append({
        'id': 'time_sync',
        'name': '时间同步',
        'requirement': '系统时间准确，日志时间戳可信',
        'current': ntp_status['message'],
        'pass': ntp_status['pass'],
        'warn': ntp_status.get('warn', False)
    })
    if not ntp_status['pass']:
        overall_pass = False

    backup_status = _check_backup()
    checks.append({
        'id': 'backup',
        'name': '日志备份',
        'requirement': '审计记录定期备份，防止意外丢失',
        'current': backup_status['message'],
        'pass': backup_status['pass']
    })
    if not backup_status['pass']:
        overall_pass = False

    integrity_status = _check_integrity()
    checks.append({
        'id': 'integrity',
        'name': '日志完整性保护',
        'requirement': '防止日志被未授权删除或修改',
        'current': integrity_status['message'],
        'pass': integrity_status['pass']
    })
    if not integrity_status['pass']:
        overall_pass = False

    access_status = _check_access_control()
    checks.append({
        'id': 'access_control',
        'name': '访问控制',
        'requirement': '仅授权人员可访问和操作日志',
        'current': access_status['message'],
        'pass': access_status['pass']
    })
    if not access_status['pass']:
        overall_pass = False

    trusted_status = _check_trusted_hosts()
    checks.append({
        'id': 'trusted_hosts',
        'name': '可信主机控制',
        'requirement': '仅可信主机可登录管理界面，防止未授权访问',
        'current': trusted_status['message'],
        'pass': trusted_status['pass'],
        'warn': trusted_status.get('warn', False)
    })
    if not trusted_status['pass']:
        overall_pass = False

    alert_status = _check_alert()
    checks.append({
        'id': 'alert',
        'name': '异常告警',
        'requirement': '对重要安全事件进行告警',
        'current': alert_status['message'],
        'pass': alert_status['pass'],
        'warn': alert_status.get('warn', False)
    })
    if not alert_status['pass']:
        overall_pass = False

    return {
        'level': '等保三级',
        'overall_pass': overall_pass,
        'checks': checks,
        'pass_count': sum(1 for c in checks if c['pass']),
        'total_count': len(checks)
    }

def _check_ntp_sync():
    import socket
    try:
        import ntplib
        client = ntplib.NTPClient()
        for server in Config.NTP_SERVERS:
            try:
                response = client.request(server, version=4, timeout=3)
                offset = abs(response.offset)
                if offset < 1.0:
                    return {
                        'pass': True,
                        'message': f'NTP同步正常（{server}，偏移 {offset:.3f} 秒）'
                    }
            except Exception:
                continue
        return {
            'pass': False,
            'message': 'NTP服务器不可达或偏移过大'
        }
    except ImportError:
        try:
            import subprocess
            result = subprocess.run(
                ['timedatectl', 'status'],
                capture_output=True, text=True, timeout=5
            )
            if 'systemd-timesyncd' in result.stdout and 'synchronized: yes' in result.stdout:
                return {
                    'pass': True,
                    'message': 'systemd-timesyncd时间同步正常'
                }
            if 'NTP synchronized: yes' in result.stdout:
                return {
                    'pass': True,
                    'message': 'NTP时间同步正常'
                }
            return {
                'pass': False,
                'warn': True,
                'message': '未检测到NTP同步（建议配置NTP服务）'
            }
        except Exception:
            return {
                'pass': False,
                'warn': True,
                'message': '无法检测NTP状态（建议配置NTP服务）'
            }

def _check_backup():
    try:
        from backup import get_backup_manager
        manager = get_backup_manager()
        info = manager.get_backup_info()
        if info['enabled'] and info['backup_count'] > 0:
            return {
                'pass': True,
                'message': f'自动备份已启用（间隔 {info["interval_hours"]} 小时，保留 {info["retention_days"]} 天，最近备份: {info["last_backup"]}）'
            }
        elif info['enabled']:
            return {
                'pass': True,
                'warn': True,
                'message': f'自动备份已配置（间隔 {info["interval_hours"]} 小时），等待首次备份'
            }
        else:
            return {
                'pass': False,
                'message': '未配置自动备份机制'
            }
    except Exception as e:
        return {
            'pass': False,
            'message': f'备份检查失败: {str(e)}'
        }

def _check_integrity():
    try:
        global db
        if db is None:
            return {
                'pass': False,
                'message': '数据库未连接'
            }
        
        integrity = db.verify_integrity()
        if integrity['valid']:
            msg = f'日志完整性校验通过（共 {integrity["total_records"]} 条记录，0 条不匹配）'
            if integrity.get('missing_checksum', 0) > 0:
                msg += f'，{integrity["missing_checksum"]} 条旧记录无校验值'
            return {
                'pass': True,
                'message': msg
            }
        else:
            return {
                'pass': False,
                'message': f'日志完整性校验失败（{integrity["mismatches"]}/{integrity["total_records"]} 条记录不匹配，可能被篡改）'
            }
    except Exception as e:
        return {
            'pass': False,
            'message': f'完整性检查失败: {str(e)}'
        }

def _check_access_control():
    try:
        if Config.AUTH_ENABLED:
            return {
                'pass': True,
                'message': f'Web界面已启用身份认证（用户名: {Config.ADMIN_USERNAME}）'
            }
        else:
            return {
                'pass': False,
                'message': 'Web界面未启用身份认证'
            }
    except Exception as e:
        return {
            'pass': False,
            'message': f'访问控制检查失败: {str(e)}'
        }

def _check_alert():
    try:
        from alert import get_alert_manager
        manager = get_alert_manager()
        info = manager.get_alert_info()
        
        if info['enabled']:
            configured_channels = []
            if info['webhook_configured']:
                configured_channels.append('Webhook')
            if info['email_configured']:
                configured_channels.append('Email')
            
            if configured_channels:
                return {
                    'pass': True,
                    'message': f'异常告警已启用，告警渠道: {", ".join(configured_channels)}'
                }
            else:
                return {
                    'pass': True,
                    'warn': True,
                    'message': '异常告警已启用，但未配置告警渠道（建议配置Webhook或邮件）'
                }
        else:
            return {
                'pass': False,
                'message': '异常告警未启用'
            }
    except Exception as e:
        return {
            'pass': False,
            'message': f'告警检查失败: {str(e)}'
        }

def _check_trusted_hosts():
    try:
        global db
        if db is None:
            return {
                'pass': False,
                'message': '数据库未连接'
            }
        
        trusted_hosts = db.get_trusted_hosts()
        enabled_hosts = [h for h in trusted_hosts if h['enabled'] == 1]
        
        if len(enabled_hosts) > 0:
            return {
                'pass': True,
                'message': f'可信主机登录白名单已启用（{len(enabled_hosts)} 台可信主机）'
            }
        else:
            return {
                'pass': False,
                'warn': True,
                'message': '未配置可信主机，所有IP均可登录管理界面（建议配置可信主机白名单）'
            }
    except Exception as e:
        return {
            'pass': False,
            'message': f'可信主机检查失败: {str(e)}'
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

@api_bp.route('/api/settings', methods=['GET'])
@login_required
def get_settings():
    settings = db.get_all_settings()
    return jsonify({
        'ntp_servers': db.get_setting('ntp_servers', ','.join(Config.NTP_SERVERS)),
        'admin_password': db.get_setting('admin_password', Config.ADMIN_PASSWORD),
        'session_timeout': int(db.get_setting('session_timeout', 3600)),
        'login_max_attempts': int(db.get_setting('login_max_attempts', 5)),
        'login_ban_duration': int(db.get_setting('login_ban_duration', 300)),
        'alert_email_enabled': db.get_setting('alert_email_enabled', Config.ALERT_EMAIL_ENABLED),
        'alert_email_smtp_server': db.get_setting('alert_email_smtp_server', Config.ALERT_EMAIL_SMTP_SERVER or ''),
        'alert_email_smtp_port': int(db.get_setting('alert_email_smtp_port', Config.ALERT_EMAIL_SMTP_PORT)),
        'alert_email_sender': db.get_setting('alert_email_sender', Config.ALERT_EMAIL_SENDER or ''),
        'alert_email_recipient': db.get_setting('alert_email_recipient', Config.ALERT_EMAIL_RECIPIENT or ''),
        'alert_email_username': db.get_setting('alert_email_username', Config.ALERT_EMAIL_USERNAME or ''),
        'alert_email_password': db.get_setting('alert_email_password', Config.ALERT_EMAIL_PASSWORD or ''),
        'alert_webhook_url': db.get_setting('alert_webhook_url', Config.ALERT_WEBHOOK_URL or ''),
        'web_host': db.get_setting('web_host', Config.WEB_HOST),
        'web_port': int(db.get_setting('web_port', Config.WEB_PORT)),
        'syslog_host': db.get_setting('syslog_host', Config.SYSLOG_HOST),
        'syslog_udp_port': int(db.get_setting('syslog_udp_port', Config.SYSLOG_UDP_PORT)),
        'syslog_tcp_port': int(db.get_setting('syslog_tcp_port', Config.SYSLOG_TCP_PORT))
    })

@api_bp.route('/api/settings', methods=['POST'])
@login_required
def update_settings():
    data = request.get_json() or {}
    username = session.get('username', 'unknown')

    config_labels = {
        'ntp_servers': 'NTP服务器',
        'admin_password': '管理员密码',
        'session_timeout': '会话超时',
        'login_max_attempts': '登录最大尝试次数',
        'login_ban_duration': '登录封禁时长',
        'alert_email_enabled': '邮件告警开关',
        'alert_email_smtp_server': '邮件SMTP服务器',
        'alert_email_smtp_port': '邮件SMTP端口',
        'alert_email_sender': '邮件发件人',
        'alert_email_recipient': '邮件收件人',
        'alert_email_username': '邮件用户名',
        'alert_email_password': '邮件密码',
        'alert_webhook_url': 'Webhook地址',
        'web_port': 'Web服务端口',
        'syslog_udp_port': 'Syslog UDP端口',
        'syslog_tcp_port': 'Syslog TCP端口',
        'syslog_host': 'Syslog监听地址'
    }

    changed = []
    for key, label in config_labels.items():
        if key in data:
            db.set_setting(key, data[key])
            changed.append(label)

    if changed:
        _write_system_log('info', 'config', f'用户 {username} 修改了系统配置',
                          f'修改项: {", ".join(changed)}')

    return jsonify({'success': True})

@api_bp.route('/api/ntp/test', methods=['POST'])
@login_required
def test_ntp():
    data = request.get_json() or {}
    ntp_servers_str = data.get('ntp_servers', db.get_setting('ntp_servers', ','.join(Config.NTP_SERVERS)))
    ntp_servers = [s.strip() for s in ntp_servers_str.split(',') if s.strip()]
    
    results = []
    overall_success = False
    
    try:
        import ntplib
        client = ntplib.NTPClient()
        for server in ntp_servers:
            try:
                response = client.request(server, version=4, timeout=3)
                offset = abs(response.offset)
                results.append({
                    'server': server,
                    'success': True,
                    'offset': offset,
                    'message': f'连接成功，偏移 {offset:.3f} 秒'
                })
                if offset < 1.0:
                    overall_success = True
            except Exception as e:
                results.append({
                    'server': server,
                    'success': False,
                    'offset': None,
                    'message': f'连接失败: {str(e)}'
                })
    except ImportError:
        try:
            import subprocess
            result = subprocess.run(
                ['timedatectl', 'status'],
                capture_output=True, text=True, timeout=5
            )
            if 'NTP synchronized: yes' in result.stdout or 'synchronized: yes' in result.stdout:
                overall_success = True
                results.append({
                    'server': 'systemd-timesyncd',
                    'success': True,
                    'offset': None,
                    'message': '系统时间同步正常'
                })
            else:
                results.append({
                    'server': 'system',
                    'success': False,
                    'offset': None,
                    'message': '系统未检测到NTP同步'
                })
        except Exception:
            results.append({
                'server': 'unknown',
                'success': False,
                'offset': None,
                'message': '无法检测NTP状态'
            })
    
    return jsonify({
        'success': overall_success,
        'results': results
    })

@api_bp.route('/api/alert/test', methods=['POST'])
@login_required
def test_email():
    data = request.get_json() or {}
    
    email_enabled = data.get('alert_email_enabled', False)
    smtp_server = data.get('alert_email_smtp_server', '')
    smtp_port = data.get('alert_email_smtp_port', 587)
    sender = data.get('alert_email_sender', '')
    recipient = data.get('alert_email_recipient', '')
    username = data.get('alert_email_username', '')
    password = data.get('alert_email_password', '')
    
    if not email_enabled:
        return jsonify({'success': False, 'message': '邮件告警未启用'})
    
    if not smtp_server or not sender or not recipient:
        return jsonify({'success': False, 'message': '请填写SMTP服务器、发件人和收件人'})
    
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        
        msg = MIMEMultipart()
        msg['From'] = sender
        msg['To'] = recipient
        msg['Subject'] = '[Syslog Server] 测试邮件'
        
        body = """
        这是一封测试邮件，用于验证邮件告警配置是否正确。
        
        如果您收到此邮件，说明邮件告警功能已正确配置。
        
        Syslog Server
        """
        msg.attach(MIMEText(body, 'plain'))
        
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(username, password)
            server.send_message(msg)
        
        return jsonify({'success': True, 'message': '测试邮件发送成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@api_bp.route('/api/trusted-hosts', methods=['GET'])
@login_required
def get_trusted_hosts():
    hosts = db.get_trusted_hosts()
    return jsonify(hosts)

@api_bp.route('/api/trusted-hosts', methods=['POST'])
@login_required
def add_trusted_host():
    data = request.get_json() or {}
    hostname = data.get('hostname', '')
    ip_address = data.get('ip_address', '')
    description = data.get('description', '')
    
    if not hostname and not ip_address:
        return jsonify({'error': '主机名或IP地址至少填写一项'}), 400
    
    host_id = db.add_trusted_host(hostname=hostname, ip_address=ip_address, description=description)
    return jsonify({'id': host_id, 'success': True})

@api_bp.route('/api/trusted-hosts/<int:host_id>', methods=['PUT'])
@login_required
def update_trusted_host_api(host_id):
    data = request.get_json() or {}
    success = db.update_trusted_host(
        host_id,
        hostname=data.get('hostname'),
        ip_address=data.get('ip_address'),
        description=data.get('description'),
        enabled=data.get('enabled')
    )
    return jsonify({'success': success})

@api_bp.route('/api/trusted-hosts/<int:host_id>', methods=['DELETE'])
@login_required
def delete_trusted_host_api(host_id):
    success = db.delete_trusted_host(host_id)
    return jsonify({'success': success})

def _get_network_interfaces():
    import netifaces
    
    interfaces = []
    for iface in netifaces.interfaces():
        addrs = netifaces.ifaddresses(iface)
        
        interface_info = {
            'name': iface,
            'ipv4': [],
            'ipv6': [],
            'mac': '',
            'status': 'unknown'
        }
        
        if netifaces.AF_INET in addrs:
            for addr in addrs[netifaces.AF_INET]:
                ip = addr.get('addr', '')
                if ip and ip != '127.0.0.1':
                    interface_info['ipv4'].append({
                        'address': ip,
                        'netmask': addr.get('netmask', ''),
                        'broadcast': addr.get('broadcast', '')
                    })
        
        if netifaces.AF_INET6 in addrs:
            for addr in addrs[netifaces.AF_INET6]:
                ip = addr.get('addr', '')
                if ip and not ip.startswith('::1'):
                    interface_info['ipv6'].append({
                        'address': ip,
                        'netmask': addr.get('netmask', ''),
                        'scope': addr.get('scope', '')
                    })
        
        if netifaces.AF_LINK in addrs:
            for addr in addrs[netifaces.AF_LINK]:
                interface_info['mac'] = addr.get('addr', '')
                break
        
        if iface.startswith('lo'):
            interface_info['status'] = 'loopback'
        elif len(interface_info['ipv4']) > 0:
            interface_info['status'] = 'up'
        else:
            interface_info['status'] = 'down'
        
        if interface_info['status'] != 'loopback':
            interfaces.append(interface_info)
    
    return interfaces

@api_bp.route('/api/network-interfaces', methods=['GET', 'PUT'])
@login_required
def network_interfaces_api():
    import subprocess
    import netifaces
    
    if request.method == 'GET':
        return jsonify(_get_network_interfaces())
    
    data = request.get_json()
    iface = data.get('interface')
    ip_address = data.get('ip_address')
    netmask = data.get('netmask', '255.255.255.0')
    
    if not iface or not ip_address:
        return jsonify({'success': False, 'error': '接口名称和IP地址不能为空'})
    
    try:
        current_ips = []
        try:
            addrs = netifaces.ifaddresses(iface)
            if netifaces.AF_INET in addrs:
                current_ips = [a.get('addr') for a in addrs[netifaces.AF_INET] if a.get('addr')]
        except Exception:
            pass
        
        for old_ip in current_ips:
            if old_ip and old_ip != '127.0.0.1':
                subprocess.run(['ip', 'addr', 'del', f'{old_ip}/{netmask}', 'dev', iface], 
                               capture_output=True, check=False)
        
        result = subprocess.run(
            ['ip', 'addr', 'add', f'{ip_address}/{netmask}', 'dev', iface],
            capture_output=True, text=True, check=False
        )
        
        if result.returncode != 0:
            return jsonify({'success': False, 'error': f'修改失败: {result.stderr}'})
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@api_bp.route('/api/static-routes', methods=['GET', 'POST'])
@login_required
def static_routes_api():
    if request.method == 'GET':
        routes = db.get_static_routes()
        return jsonify(routes)
    
    data = request.get_json()
    destination = data.get('destination', '').strip()
    gateway = data.get('gateway', '').strip()
    metric = data.get('metric', 100)
    
    if not destination or not gateway:
        return jsonify({'success': False, 'error': '目标网络和网关地址不能为空'})
    
    try:
        metric = int(metric)
    except (ValueError, TypeError):
        metric = 100
    
    route_id = db.add_static_route(destination, gateway, metric)
    return jsonify({'success': True, 'id': route_id})

@api_bp.route('/api/static-routes/<int:route_id>', methods=['PUT', 'DELETE'])
@login_required
def static_route_api(route_id):
    if request.method == 'DELETE':
        success = db.delete_static_route(route_id)
        return jsonify({'success': success})
    
    data = request.get_json()
    enabled = data.get('enabled')
    destination = data.get('destination')
    gateway = data.get('gateway')
    metric = data.get('metric')
    
    if metric is not None:
        try:
            metric = int(metric)
        except (ValueError, TypeError):
            metric = None
    
    success = db.update_static_route(
        route_id,
        destination=destination,
        gateway=gateway,
        metric=metric,
        enabled=enabled
    )
    return jsonify({'success': success})

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
