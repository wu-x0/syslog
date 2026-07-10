from flask import Blueprint, jsonify, request, render_template, Response, session, redirect, url_for, abort
from database.db import Database
from config import Config, BASE_DIR
from syslog_server.vendor_detector import get_detector
import json
import time
import os
import sys
import threading
from datetime import datetime, timedelta, timezone
from passlib.hash import bcrypt


def _get_system_timezone():
    import subprocess
    try:
        result = subprocess.run(
            ['timedatectl', 'show', '-p', 'Timezone', '--value'],
            capture_output=True, text=True, timeout=5
        )
        tz = result.stdout.strip()
        if tz:
            return tz
    except Exception:
        pass
    try:
        with open('/etc/timezone', 'r') as f:
            tz = f.read().strip()
            if tz:
                return tz
    except Exception:
        pass
    return timezone.utc
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
        # Log writing failure should not break the web UI; keep silent here
        pass


def _is_bcrypt_hash(s):
    return isinstance(s, str) and s.startswith('$2')


def login_required(f):
    def wrapper(*args, **kwargs):
        if not Config.AUTH_ENABLED:
            return f(*args, **kwargs)
        if 'logged_in' not in session or not session['logged_in']:
            return redirect(url_for('api.login'))

        # 检查 session 超时（滑动过期）：每次操作刷新时间，未操作超过 timeout 就登出
        # timeout <= 0 表示永不过期
        timeout = int(db.get_setting('session_timeout', 3600)) if db else 3600
        last_activity = session.get('last_activity', 0)
        if timeout > 0 and time.time() - last_activity > timeout:
            username = session.get('username', 'unknown')
            idle_seconds = int(time.time() - last_activity)
            _write_system_log('info', 'auth', f'用户 {username} 因长时间未操作被登出', f'空闲时长: {idle_seconds}秒, 超时设置: {timeout}秒')
            session.clear()
            return redirect(url_for('api.login'))

        # 每次操作都刷新活动时间
        session['last_activity'] = time.time()

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

        # 优先读取已存储的哈希；向后兼容老的明文设置
        stored_hash = db.get_setting('admin_password_hash', None) if db else None
        stored_plain = db.get_setting('admin_password', Config.ADMIN_PASSWORD) if db else Config.ADMIN_PASSWORD
        # 是否显示默认凭据提示（仅当存在明文默认密码时）
        is_default_password = (stored_hash is None and stored_plain and stored_plain == Config.ADMIN_PASSWORD and Config.ADMIN_PASSWORD)

        if db and hasattr(db, 'is_ip_banned') and db.is_ip_banned(client_ip, ban_duration):
            return render_template('login.html', error=f'您的IP ({client_ip}) 因多次登录失败已被临时封禁，请稍后再试', show_default_credentials=bool(is_default_password))

        username = request.form.get('username')
        password = request.form.get('password')

        if username == Config.ADMIN_USERNAME:
            authenticated = False
            try:
                if stored_hash and _is_bcrypt_hash(stored_hash):
                    authenticated = bcrypt.verify(password, stored_hash)
                elif stored_plain:
                    # 兼容旧明文密码：如果匹配则立即迁移到哈希存储
                    if password == stored_plain:
                        authenticated = True
                        try:
                            new_hash = bcrypt.hash(password)
                            db.set_setting('admin_password_hash', new_hash)
                            # 清除明文存储以降低泄露风险
                            db.set_setting('admin_password', '')
                        except Exception:
                            pass
                else:
                    authenticated = False
            except Exception:
                authenticated = False

            if authenticated:
                # 登录成功，清除失败记录
                if db and hasattr(db, 'clear_login_failures'):
                    db.clear_login_failures(client_ip)
                session['logged_in'] = True
                session['username'] = username
                session['last_activity'] = time.time()
                _write_system_log('info', 'auth', f'用户 {username} 登录成功', f'登录IP: {client_ip}')

                # 如果仍使用默认明文密码（仅开发场景），强制修改密码
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
                        return render_template('login.html', error=f'您的IP ({client_ip}) 因连续{max_attempts}次登录失败已被封禁{ban_duration}秒', show_default_credentials=bool(is_default_password))
                return render_template('login.html', error='用户名或密码错误', show_default_credentials=bool(is_default_password))

    stored_hash = db.get_setting('admin_password_hash', None) if db else None
    stored_plain = db.get_setting('admin_password', Config.ADMIN_PASSWORD) if db else Config.ADMIN_PASSWORD
    is_default_password = (stored_hash is None and stored_plain and stored_plain == Config.ADMIN_PASSWORD and Config.ADMIN_PASSWORD)
    timeout_msg = request.args.get('timeout')
    return render_template('login.html', show_default_credentials=bool(is_default_password), timeout=timeout_msg)


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
        if new_password == Config.ADMIN_PASSWORD and Config.ADMIN_PASSWORD:
            return render_template('change_password.html', error='新密码不能与默认密码相同')
        if db:
            try:
                hashed = bcrypt.hash(new_password)
                db.set_setting('admin_password_hash', hashed)
                # 清除可能存在的明文配置
                db.set_setting('admin_password', '')
            except Exception:
                return render_template('change_password.html', error='无法保存新密码，请稍后重试')
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

# rest of file unchanged
