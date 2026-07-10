@@
*** Begin Patch
*** Update File: syslog-server/config.py
@@
-    AUTH_ENABLED = True
-    ADMIN_USERNAME = 'admin'
-    ADMIN_PASSWORD = 'syslog@2024'
-    SESSION_SECRET_KEY = 'syslog-server-secret-key-change-in-production'
+    AUTH_ENABLED = True
+    ADMIN_USERNAME = os.environ.get('SYSLOG_ADMIN_USERNAME', 'admin')
+    # ADMIN_PASSWORD should NOT be stored in plaintext. Prefer hashed password stored in DB.
+    # The application will read the admin password hash from the settings table or environment.
+    # For development only, an env var SYSLOG_ADMIN_PASSWORD may be used; in production set admin password via the web UI or DB.
+    ADMIN_PASSWORD = os.environ.get('SYSLOG_ADMIN_PASSWORD', '')
+    # SESSION_SECRET_KEY: prefer providing via environment. If not set, generate a random key at runtime (not persisted).
+    SESSION_SECRET_KEY = os.environ.get('SESSION_SECRET_KEY') or None
*** End Patch
