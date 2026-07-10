@@
-import socket
-import threading
-import queue
-from syslog_server.parser import parse_syslog_message
-
-class UDPSyslogServer:
-    def __init__(self, host, port, log_queue):
-        self.host = host
-        self.port = port
-        self.log_queue = log_queue
-        self.sock = None
-        self.running = False
-        self.thread = None
-    
-    def start(self):
-        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
-        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
-        self.sock.bind((self.host, self.port))
-        self.running = True
-        self.thread = threading.Thread(target=self._serve, daemon=True)
-        self.thread.start()
-        print(f"UDP Syslog server listening on {self.host}:{self.port}")
-    
-    def _serve(self):
-        while self.running:
-            try:
-                data, addr = self.sock.recvfrom(65535)
-                message = data.decode('utf-8', errors='replace')
-                source_ip = addr[0]
-                
-                parsed = parse_syslog_message(message, source_ip)
-                if parsed:
-                    try:
-                        self.log_queue.put_nowait(parsed)
-                    except queue.Full:
-                        pass
-            except Exception as e:
-                if self.running:
-                    print(f"UDP server error: {e}")
-    
-    def stop(self):
-        self.running = False
-        if self.sock:
-            self.sock.close()
-        if self.thread:
-            self.thread.join(timeout=2)
-        print("UDP Syslog server stopped")
+import socket
+import threading
+import queue
+from syslog_server.parser import parse_syslog_message
+from logging import getLogger
+import time
+
+logger = getLogger('syslogserver.udp')
+
+
+class UDPSyslogServer:
+    def __init__(self, host, port, log_queue, recv_buf=65535, rate_limit_per_ip=100):
+        self.host = host
+        self.port = port
+        self.log_queue = log_queue
+        self.recv_buf = recv_buf
+        self.sock = None
+        self.running = False
+        self.thread = None
+        self._rate_limit_per_ip = rate_limit_per_ip
+        self._ip_counters = {}
+
+    def start(self):
+        try:
+            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
+            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
+            self.sock.bind((self.host, self.port))
+            self.running = True
+            self.thread = threading.Thread(target=self._serve, daemon=True)
+            self.thread.start()
+            logger.info("UDP Syslog server listening on %s:%s", self.host, self.port)
+        except Exception:
+            logger.exception("Failed to start UDP server")
+
+    def _serve(self):
+        while self.running:
+            try:
+                data, addr = self.sock.recvfrom(self.recv_buf)
+                message = data.decode('utf-8', errors='replace')
+                source_ip = addr[0]
+
+                # basic per-ip rate limiting (simple token-bucket approximation)
+                now = int(time.time())
+                cnt = self._ip_counters.get(source_ip, {'ts': now, 'count': 0})
+                if cnt['ts'] != now:
+                    cnt = {'ts': now, 'count': 0}
+                cnt['count'] += 1
+                self._ip_counters[source_ip] = cnt
+                if cnt['count'] > self._rate_limit_per_ip:
+                    logger.warning("Rate limit exceeded for %s: %s msgs/s", source_ip, cnt['count'])
+                    continue
+
+                parsed = None
+                try:
+                    parsed = parse_syslog_message(message, source_ip)
+                except Exception:
+                    logger.exception("Failed to parse UDP syslog message from %s: %s", source_ip, message)
+                    continue
+
+                if parsed:
+                    try:
+                        self.log_queue.put_nowait(parsed)
+                    except queue.Full:
+                        logger.warning("Log queue full, dropping UDP message from %s", source_ip)
+            except Exception:
+                if self.running:
+                    logger.exception("UDP server error")
+            time.sleep(0.001)
+
+    def stop(self):
+        self.running = False
+        if self.sock:
+            try:
+                self.sock.close()
+            except Exception:
+                logger.exception("Error closing UDP socket")
+        if self.thread:
+            self.thread.join(timeout=2)
+        logger.info("UDP Syslog server stopped")
