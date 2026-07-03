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
    
    print(f"\n{'='*50}")
    print("  Syslog 日志服务器已启动")
    print(f"{'='*50}")
    print(f"  UDP 端口:  {syslog_udp_port}")
    print(f"  TCP 端口:  {syslog_tcp_port}")
    print(f"  Web 界面:  http://{web_host}:{web_port}")
    print(f"  数据库:    {Config.DATABASE_PATH}")
    print(f"{'='*50}\n")
    
    app.run(
        host=web_host,
        port=web_port,
        debug=Config.DEBUG,
        use_reloader=False,
        threaded=True
    )

if __name__ == '__main__':
    main()
