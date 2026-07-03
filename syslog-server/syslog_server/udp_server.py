import socket
import threading
import queue
from syslog_server.parser import parse_syslog_message

class UDPSyslogServer:
    def __init__(self, host, port, log_queue):
        self.host = host
        self.port = port
        self.log_queue = log_queue
        self.sock = None
        self.running = False
        self.thread = None
    
    def start(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))
        self.running = True
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()
        print(f"UDP Syslog server listening on {self.host}:{self.port}")
    
    def _serve(self):
        while self.running:
            try:
                data, addr = self.sock.recvfrom(65535)
                message = data.decode('utf-8', errors='replace')
                source_ip = addr[0]
                
                parsed = parse_syslog_message(message, source_ip)
                if parsed:
                    try:
                        self.log_queue.put_nowait(parsed)
                    except queue.Full:
                        pass
            except Exception as e:
                if self.running:
                    print(f"UDP server error: {e}")
    
    def stop(self):
        self.running = False
        if self.sock:
            self.sock.close()
        if self.thread:
            self.thread.join(timeout=2)
        print("UDP Syslog server stopped")
