import os
import sys
import queue
import signal
import threading
from flask import Flask

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from syslog_server.udp_server import UDPSyslogServer
from syslog_server.tcp_server import TCPSyslogServer
from database.db import Database, LogWriter
from web.api import api_bp, init_api
from backup import start_backup
from alert import start_alert

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
    
    log_writer = LogWriter(log_queue, db)
    log_writer.start()
    
    udp_server = UDPSyslogServer(
        Config.SYSLOG_HOST,
        Config.SYSLOG_UDP_PORT,
        log_queue
    )
    udp_server.db = db
    udp_server.start()
    
    tcp_server = TCPSyslogServer(
        Config.SYSLOG_HOST,
        Config.SYSLOG_TCP_PORT,
        log_queue
    )
    tcp_server.db = db
    tcp_server.start()
    
    init_api(db, log_queue)
    app.register_blueprint(api_bp)
    
    start_backup()
    start_alert()
    
    def signal_handler(sig, frame):
        print("\nShutting down...")
        udp_server.stop()
        tcp_server.stop()
        log_writer.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    print(f"\n{'='*50}")
    print("  Syslog 日志服务器已启动")
    print(f"{'='*50}")
    print(f"  UDP 端口:  {Config.SYSLOG_UDP_PORT}")
    print(f"  TCP 端口:  {Config.SYSLOG_TCP_PORT}")
    print(f"  Web 界面:  http://{Config.WEB_HOST}:{Config.WEB_PORT}")
    print(f"  数据库:    {Config.DATABASE_PATH}")
    print(f"{'='*50}\n")
    
    app.run(
        host=Config.WEB_HOST,
        port=Config.WEB_PORT,
        debug=Config.DEBUG,
        use_reloader=False,
        threaded=True
    )

if __name__ == '__main__':
    main()
