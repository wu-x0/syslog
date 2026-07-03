import socket
import threading
import queue
from syslog_server.parser import parse_syslog_message

class TCPSyslogServer:
    def __init__(self, host, port, log_queue):
        self.host = host
        self.port = port
        self.log_queue = log_queue
        self.sock = None
        self.running = False
        self.thread = None
        self.clients = []
        self.db = None
    
    def start(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))
        self.sock.listen(50)
        self.running = True
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()
        print(f"TCP Syslog server listening on {self.host}:{self.port}")
    
    def _serve(self):
        while self.running:
            try:
                conn, addr = self.sock.accept()
                
                if self.db and hasattr(self.db, 'is_trusted_host'):
                    if not self.db.is_trusted_host(ip_address=addr[0]):
                        conn.close()
                        continue
                
                client_thread = threading.Thread(
                    target=self._handle_client,
                    args=(conn, addr),
                    daemon=True
                )
                client_thread.start()
                self.clients.append(conn)
            except Exception as e:
                if self.running:
                    print(f"TCP server accept error: {e}")
    
    def _handle_client(self, conn, addr):
        source_ip = addr[0]
        buffer = ''
        try:
            while self.running:
                data = conn.recv(4096)
                if not data:
                    break
                
                buffer += data.decode('utf-8', errors='replace')
                
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    line = line.strip()
                    if line:
                        parsed = parse_syslog_message(line, source_ip)
                        if parsed:
                            try:
                                self.log_queue.put_nowait(parsed)
                            except queue.Full:
                                pass
        except Exception as e:
            pass
        finally:
            conn.close()
            if conn in self.clients:
                self.clients.remove(conn)
    
    def stop(self):
        self.running = False
        for client in self.clients[:]:
            try:
                client.close()
            except:
                pass
        if self.sock:
            self.sock.close()
        if self.thread:
            self.thread.join(timeout=2)
        print("TCP Syslog server stopped")
