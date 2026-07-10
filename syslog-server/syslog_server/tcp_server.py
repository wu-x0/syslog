@@
-import socket
-import threading
-import queue
-from syslog_server.parser import parse_syslog_message
-
-class TCPSyslogServer:
-    def __init__(self, host, port, log_queue):
-        self.host = host
-        self.port = port
-        self.log_queue = log_queue
-        self.sock = None
-        self.running = False
-        self.thread = None
-        self.clients = []
-    
-    def start(self):
-        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
-        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
-        self.sock.bind((self.host, self.port))
-        self.sock.listen(50)
-        self.running = True
-        self.thread = threading.Thread(target=self._serve, daemon=True)
-        self.thread.start()
-        print(f"TCP Syslog server listening on {self.host}:{self.port}")
-    
-    def _serve(self):
-        while self.running:
-            try:
-                conn, addr = self.sock.accept()
-                
-                client_thread = threading.Thread(
-                    target=self._handle_client,
-                    args=(conn, addr),
-                    daemon=True
-                )
-                client_thread.start()
-                self.clients.append(conn)
-            except Exception as e:
-                if self.running:
-                    print(f"TCP server accept error: {e}")
-    
-    def _handle_client(self, conn, addr):
-        source_ip = addr[0]
-        buffer = ''
-        try:
-            while self.running:
-                data = conn.recv(4096)
-                if not data:
-                    break
-                
-                buffer += data.decode('utf-8', errors='replace')
-                
-                while '\n' in buffer:
-                    line, buffer = buffer.split('\n', 1)
-                    line = line.strip()
-                    if line:
-                        parsed = parse_syslog_message(line, source_ip)
-                        if parsed:
-                            try:
-                                self.log_queue.put_nowait(parsed)
-                            except queue.Full:
-                                pass
-        except Exception as e:
-            pass
-        finally:
-            conn.close()
-            if conn in self.clients:
-                self.clients.remove(conn)
-    
-    def stop(self):
-        self.running = False
-        for client in self.clients[:]:
-            try:
-                client.close()
-            except:
-                pass
-        if self.sock:
-            self.sock.close()
-        if self.thread:
-            self.thread.join(timeout=2)
-        print("TCP Syslog server stopped")
+import socket
+import threading
+import queue
+import time
+from syslog_server.parser import parse_syslog_message
+from logging import getLogger
+
+logger = getLogger('syslogserver.tcp')
+
+
+class TCPSyslogServer:
+    def __init__(self, host, port, log_queue, backlog=50, client_timeout=30):
+        self.host = host
+        self.port = port
+        self.log_queue = log_queue
+        self.sock = None
+        self.running = False
+        self.thread = None
+        self.clients = []
+        self.backlog = backlog
+        self.client_timeout = client_timeout
+
+    def start(self):
+        try:
+            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
+            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
+            self.sock.bind((self.host, self.port))
+            self.sock.listen(self.backlog)
+            self.running = True
+            self.thread = threading.Thread(target=self._serve, daemon=True)
+            self.thread.start()
+            logger.info("TCP Syslog server listening on %s:%s", self.host, self.port)
+        except Exception:
+            logger.exception("Failed to start TCP server")
+
+    def _serve(self):
+        while self.running:
+            try:
+                conn, addr = self.sock.accept()
+                conn.settimeout(self.client_timeout)
+
+                client_thread = threading.Thread(
+                    target=self._handle_client,
+                    args=(conn, addr),
+                    daemon=True
+                )
+                client_thread.start()
+                self.clients.append(conn)
+            except Exception:
+                if self.running:
+                    logger.exception("TCP server accept error")
+            time.sleep(0.01)
+
+    def _handle_client(self, conn, addr):
+        source_ip = addr[0]
+        buffer = ''
+        try:
+            while self.running:
+                try:
+                    data = conn.recv(4096)
+                except socket.timeout:
+                    continue
+                except Exception:
+                    logger.exception("Error reading from client %s", addr)
+                    break
+
+                if not data:
+                    break
+
+                buffer += data.decode('utf-8', errors='replace')
+
+                while '\n' in buffer:
+                    line, buffer = buffer.split('\n', 1)
+                    line = line.strip()
+                    if line:
+                        parsed = None
+                        try:
+                            parsed = parse_syslog_message(line, source_ip)
+                        except Exception:
+                            logger.exception("Failed to parse syslog message from %s: %s", source_ip, line)
+                            continue
+                        if parsed:
+                            try:
+                                self.log_queue.put_nowait(parsed)
+                            except queue.Full:
+                                logger.warning("Log queue full, dropping message from %s", source_ip)
+        except Exception:
+            logger.exception("Unexpected error handling client %s", addr)
+        finally:
+            try:
+                conn.close()
+            except Exception:
+                logger.exception("Error closing client connection %s", addr)
+            if conn in self.clients:
+                try:
+                    self.clients.remove(conn)
+                except ValueError:
+                    pass
+
+    def stop(self):
+        self.running = False
+        for client in list(self.clients):
+            try:
+                client.close()
+            except Exception:
+                logger.exception("Error closing client socket")
+        if self.sock:
+            try:
+                self.sock.close()
+            except Exception:
+                logger.exception("Error closing server socket")
+        if self.thread:
+            self.thread.join(timeout=2)
+        logger.info("TCP Syslog server stopped")
