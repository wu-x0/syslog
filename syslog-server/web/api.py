@@
*** Begin Patch
*** Update File: syslog-server/web/api.py
@@
-    settings = db.get_all_settings()
-    return jsonify({
-        'version': Config.VERSION,
-        'build_date': Config.BUILD_DATE,
-        'db_path': Config.DATABASE_PATH,
-        'system_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
-        'system_timezone': _get_system_timezone(),
-        'ntp_servers': db.get_setting('ntp_servers', ','.join(Config.NTP_SERVERS)),
-        'admin_password': db.get_setting('admin_password', Config.ADMIN_PASSWORD),
-        'session_timeout': int(db.get_setting('session_timeout', 3600)),
-        'login_max_attempts': int(db.get_setting('login_max_attempts', 5)),
-        'login_ban_duration': int(db.get_setting('login_ban_duration', 300)),
-        'alert_email_enabled': db.get_setting('alert_email_enabled', Config.ALERT_EMAIL_ENABLED),
-        'alert_email_smtp_server': db.get_setting('alert_email_smtp_server', Config.ALERT_EMAIL_SMTP_SERVER or ''),
-        'alert_email_smtp_port': int(db.get_setting('alert_email_smtp_port', Config.ALERT_EMAIL_SMTP_PORT)),
-        'alert_email_sender': db.get_setting('alert_email_sender', Config.ALERT_EMAIL_SENDER or ''),
-        'alert_email_recipient': db.get_setting('alert_email_recipient', Config.ALERT_EMAIL_RECIPIENT or ''),
-        'alert_email_username': db.get_setting('alert_email_username', Config.ALERT_EMAIL_USERNAME or ''),
-        'alert_email_password': db.get_setting('alert_email_password', Config.ALERT_EMAIL_PASSWORD or ''),
-        'alert_webhook_url': db.get_setting('alert_webhook_url', Config.ALERT_WEBHOOK_URL or ''),
-        'web_host': db.get_setting('web_host', Config.WEB_HOST),
-        'web_port': int(db.get_setting('web_port', Config.WEB_PORT)),
-        'syslog_host': db.get_setting('syslog_host', Config.SYSLOG_HOST),
-        'syslog_udp_port': int(db.get_setting('syslog_udp_port', Config.SYSLOG_UDP_PORT)),
-        'syslog_tcp_port': int(db.get_setting('syslog_tcp_port', Config.SYSLOG_TCP_PORT))
-    })
+    # Return settings but avoid including any plaintext or hashed passwords
+    settings = db.get_all_settings()
+    return jsonify({
+        'version': Config.VERSION,
+        'build_date': Config.BUILD_DATE,
+        'db_path': Config.DATABASE_PATH,
+        'system_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
+        'system_timezone': _get_system_timezone(),
+        'ntp_servers': db.get_setting('ntp_servers', ','.join(Config.NTP_SERVERS)),
+        'session_timeout': int(db.get_setting('session_timeout', 3600)),
+        'login_max_attempts': int(db.get_setting('login_max_attempts', 5)),
+        'login_ban_duration': int(db.get_setting('login_ban_duration', 300)),
+        'alert_email_enabled': db.get_setting('alert_email_enabled', Config.ALERT_EMAIL_ENABLED),
+        'alert_email_smtp_server': db.get_setting('alert_email_smtp_server', Config.ALERT_EMAIL_SMTP_SERVER or ''),
+        'alert_email_smtp_port': int(db.get_setting('alert_email_smtp_port', Config.ALERT_EMAIL_SMTP_PORT)),
+        'alert_email_sender': db.get_setting('alert_email_sender', Config.ALERT_EMAIL_SENDER or ''),
+        'alert_email_recipient': db.get_setting('alert_email_recipient', Config.ALERT_EMAIL_RECIPIENT or ''),
+        'alert_email_username': db.get_setting('alert_email_username', Config.ALERT_EMAIL_USERNAME or ''),
+        # Do NOT return alert_email_password or admin_password/admin_password_hash
+        'alert_webhook_url': db.get_setting('alert_webhook_url', Config.ALERT_WEBHOOK_URL or ''),
+        'web_host': db.get_setting('web_host', Config.WEB_HOST),
+        'web_port': int(db.get_setting('web_port', Config.WEB_PORT)),
+        'syslog_host': db.get_setting('syslog_host', Config.SYSLOG_HOST),
+        'syslog_udp_port': int(db.get_setting('syslog_udp_port', Config.SYSLOG_UDP_PORT)),
+        'syslog_tcp_port': int(db.get_setting('syslog_tcp_port', Config.SYSLOG_TCP_PORT))
+    })
*** End Patch
