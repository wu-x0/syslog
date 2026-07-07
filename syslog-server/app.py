import os
import sys
import queue
import signal
import threading
import subprocess
import tempfile
from datetime import datetime, timedelta
from flask import Flask

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config, BASE_DIR
from syslog_server.udp_server import UDPSyslogServer
from syslog_server.tcp_server import TCPSyslogServer
from database.db import Database, LogWriter
from web.api import api_bp, init_api
from backup import start_backup
from alert import start_alert

CERT_DIR = os.path.join(BASE_DIR, 'certs')
CERT_FILE = os.path.join(CERT_DIR, 'cert.pem')
KEY_FILE = os.path.join(CERT_DIR, 'key.pem')


def _generate_self_signed_cert():
    if os.path.exists(CERT_FILE) and os.path.exists(KEY_FILE):
        return

    os.makedirs(CERT_DIR, exist_ok=True)

    try:
        subprocess.run([
            'openssl', 'req', '-x509', '-newkey', 'rsa:2048',
            '-keyout', KEY_FILE,
            '-out', CERT_FILE,
            '-days', '3650',
            '-nodes',
            '-subj', '/C=CN/ST=Beijing/L=Beijing/O=SyslogServer/CN=syslog-server'
        ], check=True, capture_output=True, timeout=30)
        os.chmod(KEY_FILE, 0o600)
        os.chmod(CERT_FILE, 0o644)
        print(f"[SSL] 自签名证书已生成: {CERT_FILE}")
        return
    except Exception:
        pass

    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, u'CN'),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, u'Beijing'),
            x509.NameAttribute(NameOID.LOCALITY_NAME, u'Beijing'),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, u'SyslogServer'),
            x509.NameAttribute(NameOID.COMMON_NAME, u'syslog-server'),
        ])
        cert = x509.CertificateBuilder().subject_name(subject).issuer_name(
            issuer).public_key(key.public_key()).serial_number(
            x509.random_serial_number()).not_valid_before(
            datetime.utcnow()).not_valid_after(
            datetime.utcnow() + timedelta(days=3650)).sign(key, hashes.SHA256())

        with open(KEY_FILE, 'wb') as f:
            f.write(key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()))
        os.chmod(KEY_FILE, 0o600)

        with open(CERT_FILE, 'wb') as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
        os.chmod(CERT_FILE, 0o644)

        print(f"[SSL] 自签名证书已生成 (cryptography): {CERT_FILE}")
    except ImportError:
        print("[SSL] 警告: 无法生成证书 (缺少 openssl 和 cryptography), HTTPS 不可用")


def create_app():
    template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'web', 'templates')
    
    app = Flask(__name__, template_folder=template_dir)
    app.config.from_object(Config)
    app.secret_key = Config.SESSION_SECRET_KEY
    
    return app

def main():
    app = create_app()
    
    log_queue = queue.Queue(maxsize=Config.LOG_QUEUE_MAXSIZE)
    
    db = Database(Config.DATABASE_PATH)
    
    syslog_host = db.get_setting('syslog_host', Config.SYSLOG_HOST)
    syslog_udp_port = int(db.get_setting('syslog_udp_port', Config.SYSLOG_UDP_PORT))
    syslog_tcp_port = int(db.get_setting('syslog_tcp_port', Config.SYSLOG_TCP_PORT))
    web_host = db.get_setting('web_host', Config.WEB_HOST)
    web_port = int(db.get_setting('web_port', Config.WEB_PORT))
    
    log_writer = LogWriter(log_queue, db)
    log_writer.start()
    
    udp_server = UDPSyslogServer(
        syslog_host,
        syslog_udp_port,
        log_queue
    )
    udp_server.start()
    
    tcp_server = TCPSyslogServer(
        syslog_host,
        syslog_tcp_port,
        log_queue
    )
    tcp_server.start()
    
    init_api(db, log_queue)
    app.register_blueprint(api_bp)
    
    start_backup(db=db)
    start_alert(db=db)
    
    def signal_handler(sig, frame):
        print("\nShutting down...")
        udp_server.stop()
        tcp_server.stop()
        log_writer.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    use_ssl = False
    if web_port == 443:
        _generate_self_signed_cert()
        if os.path.exists(CERT_FILE) and os.path.exists(KEY_FILE):
            use_ssl = True
    
    protocol = 'https' if use_ssl else 'http'
    ssl_context = (CERT_FILE, KEY_FILE) if use_ssl else None
    
    print(f"\n{'='*50}")
    print("  Syslog 日志服务器已启动")
    print(f"{'='*50}")
    print(f"  UDP 端口:  {syslog_udp_port}")
    print(f"  TCP 端口:  {syslog_tcp_port}")
    print(f"  Web 界面:  {protocol}://{web_host}:{web_port}")
    print(f"  数据库:    {Config.DATABASE_PATH}")
    print(f"{'='*50}\n")

    try:
        db.add_system_log('info', 'system', 'Syslog 日志服务器已启动',
                          f'UDP端口: {syslog_udp_port}, TCP端口: {syslog_tcp_port}, Web端口: {web_port}')
    except Exception:
        pass
    
    app.run(
        host=web_host,
        port=web_port,
        debug=Config.DEBUG,
        use_reloader=False,
        threaded=True,
        ssl_context=ssl_context
    )

if __name__ == '__main__':
    main()
