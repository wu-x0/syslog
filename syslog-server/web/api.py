from flask import Blueprint, jsonify, request, render_template, Response
from database.db import Database
from config import Config
import json
import time
from datetime import datetime

api_bp = Blueprint('api', __name__)
db = None
log_queue = None

def init_api(database, queue):
    global db, log_queue
    db = database
    log_queue = queue

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
    return jsonify(stats)

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
        while True:
            try:
                logs = db.get_recent_logs(limit=50)
                new_logs = [log for log in logs if log['id'] > last_id]
                if new_logs:
                    last_id = new_logs[0]['id']
                    for log in reversed(new_logs):
                        yield f"data: {json.dumps(log)}\n\n"
                time.sleep(1)
            except GeneratorExit:
                break
            except:
                time.sleep(1)
    
    return Response(event_stream(), mimetype='text/event-stream')

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
    return jsonify({
        'udp_port': Config.SYSLOG_UDP_PORT,
        'tcp_port': Config.SYSLOG_TCP_PORT,
        'web_port': Config.WEB_PORT,
        'facilities': Config.FACILITY_MAP,
        'severities': Config.SEVERITY_MAP,
        'severity_colors': Config.SEVERITY_COLORS
    })
