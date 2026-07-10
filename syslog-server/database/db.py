@@
*** Begin Patch
*** Update File: syslog-server/database/db.py
@@
-import sqlite3
-import threading
-import queue
-import time
-import hashlib
-from datetime import datetime, timedelta
-from config import Config
+import sqlite3
+import threading
+import queue
+import time
+import hashlib
+import logging
+from datetime import datetime, timedelta
+from config import Config
+
+logger = logging.getLogger('syslogserver.db')
@@
     def insert_log(self, log_data):
         conn = self._get_conn()
         cursor = conn.cursor()
         checksum = self._compute_checksum(log_data)
         cursor.execute('''
@@
         conn.commit()
         return cursor.lastrowid
@@
     def insert_many_logs(self, logs_list):
         if not logs_list:
             return
-        conn = self._get_conn()
-        cursor = conn.cursor()
-        cursor.executemany('''
-            INSERT INTO syslogs (
-                received_at, timestamp, facility, facility_str, severity,
-                severity_str, hostname, source_ip, app_name, proc_id,
-                message, raw_message, vendor, vendor_name, checksum
-            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
-        ''', [(
-            log['received_at'],
-            log['timestamp'],
-            log['facility'],
-            log['facility_str'],
-            log['severity'],
-            log['severity_str'],
-            log['hostname'],
-            log['source_ip'],
-            log['app_name'],
-            log['proc_id'],
-            log['message'],
-            log['raw_message'],
-            log.get('vendor', 'other'),
-            log.get('vendor_name', '其他'),
-            self._compute_checksum(log)
-        ) for log in logs_list])
-        conn.commit()
+        conn = self._get_conn()
+        cursor = conn.cursor()
+        values = []
+        for log in logs_list:
+            values.append((
+                log['received_at'],
+                log['timestamp'],
+                log['facility'],
+                log['facility_str'],
+                log['severity'],
+                log['severity_str'],
+                log['hostname'],
+                log['source_ip'],
+                log['app_name'],
+                log['proc_id'],
+                log['message'],
+                log['raw_message'],
+                log.get('vendor', 'other'),
+                log.get('vendor_name', '其他'),
+                self._compute_checksum(log)
+            ))
+
+        try:
+            cursor.executemany('''
+                INSERT INTO syslogs (
+                    received_at, timestamp, facility, facility_str, severity,
+                    severity_str, hostname, source_ip, app_name, proc_id,
+                    message, raw_message, vendor, vendor_name, checksum
+                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
+            ''', values)
+            conn.commit()
+            logger.debug('insert_many_logs: inserted %d logs', len(values))
+        except Exception:
+            logger.exception('insert_many_logs failed, attempting rollback')
+            try:
+                conn.rollback()
+            except Exception:
+                logger.exception('rollback failed')
+            raise
*** End Patch
