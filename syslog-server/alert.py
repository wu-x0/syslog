import requests
import threading
import time
from datetime import datetime
from config import Config

class AlertManager:
    def __init__(self, db=None):
        self.db = db
        self.running = False
        self.thread = None
        self.alert_history = []
        self.last_alerts = {}
        if db:
            self._load_config()
    
    def _load_config(self):
        try:
            self.webhook_url = self.db.get_setting('alert_webhook_url', Config.ALERT_WEBHOOK_URL or '')
            self.email_enabled = bool(self.db.get_setting('alert_email_enabled', Config.ALERT_EMAIL_ENABLED))
            self.email_smtp_server = self.db.get_setting('alert_email_smtp_server', Config.ALERT_EMAIL_SMTP_SERVER or '')
            self.email_smtp_port = int(self.db.get_setting('alert_email_smtp_port', Config.ALERT_EMAIL_SMTP_PORT))
            self.email_sender = self.db.get_setting('alert_email_sender', Config.ALERT_EMAIL_SENDER or '')
            self.email_recipient = self.db.get_setting('alert_email_recipient', Config.ALERT_EMAIL_RECIPIENT or '')
            self.email_username = self.db.get_setting('alert_email_username', Config.ALERT_EMAIL_USERNAME or '')
            self.email_password = self.db.get_setting('alert_email_password', Config.ALERT_EMAIL_PASSWORD or '')
        except Exception:
            self.webhook_url = Config.ALERT_WEBHOOK_URL
            self.email_enabled = Config.ALERT_EMAIL_ENABLED
            self.email_smtp_server = Config.ALERT_EMAIL_SMTP_SERVER
            self.email_smtp_port = Config.ALERT_EMAIL_SMTP_PORT
            self.email_sender = Config.ALERT_EMAIL_SENDER
            self.email_recipient = Config.ALERT_EMAIL_RECIPIENT
            self.email_username = Config.ALERT_EMAIL_USERNAME
            self.email_password = Config.ALERT_EMAIL_PASSWORD
    
    def get_webhook_url(self):
        if self.db:
            return self.db.get_setting('alert_webhook_url', Config.ALERT_WEBHOOK_URL or '')
        return Config.ALERT_WEBHOOK_URL
    
    def is_email_enabled(self):
        if self.db:
            return bool(self.db.get_setting('alert_email_enabled', Config.ALERT_EMAIL_ENABLED))
        return Config.ALERT_EMAIL_ENABLED
    
    def get_email_config(self):
        if self.db:
            return {
                'smtp_server': self.db.get_setting('alert_email_smtp_server', Config.ALERT_EMAIL_SMTP_SERVER or ''),
                'smtp_port': int(self.db.get_setting('alert_email_smtp_port', Config.ALERT_EMAIL_SMTP_PORT)),
                'sender': self.db.get_setting('alert_email_sender', Config.ALERT_EMAIL_SENDER or ''),
                'recipient': self.db.get_setting('alert_email_recipient', Config.ALERT_EMAIL_RECIPIENT or ''),
                'username': self.db.get_setting('alert_email_username', Config.ALERT_EMAIL_USERNAME or ''),
                'password': self.db.get_setting('alert_email_password', Config.ALERT_EMAIL_PASSWORD or '')
            }
        return {
            'smtp_server': Config.ALERT_EMAIL_SMTP_SERVER,
            'smtp_port': Config.ALERT_EMAIL_SMTP_PORT,
            'sender': Config.ALERT_EMAIL_SENDER,
            'recipient': Config.ALERT_EMAIL_RECIPIENT,
            'username': Config.ALERT_EMAIL_USERNAME,
            'password': Config.ALERT_EMAIL_PASSWORD
        }
    
    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        print("Alert manager started")
    
    def _run(self):
        while self.running:
            try:
                self._check_disk_space()
                time.sleep(300)
            except Exception as e:
                print(f"Alert manager error: {e}")
    
    def send_alert(self, alert_type, message, level='warning', details=None):
        if not Config.ALERT_ENABLED:
            return False
        
        alert_id = f"{alert_type}_{int(time.time())}"
        alert = {
            'id': alert_id,
            'type': alert_type,
            'message': message,
            'level': level,
            'details': details or {},
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        self.alert_history.append(alert)
        if len(self.alert_history) > 100:
            self.alert_history = self.alert_history[-100:]
        
        sent = False
        webhook_url = self.get_webhook_url()
        if webhook_url:
            sent |= self._send_webhook(alert, webhook_url)
        
        if self.is_email_enabled():
            email_config = self.get_email_config()
            sent |= self._send_email(alert, email_config)
        
        return sent
    
    def _send_webhook(self, alert, webhook_url):
        try:
            payload = {
                'alert': alert,
                'timestamp': alert['timestamp']
            }
            response = requests.post(
                webhook_url,
                json=payload,
                timeout=10
            )
            return response.status_code == 200
        except Exception as e:
            print(f"Webhook alert failed: {e}")
            return False
    
    def _send_email(self, alert, email_config):
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            
            msg = MIMEMultipart()
            msg['From'] = email_config['sender']
            msg['To'] = email_config['recipient']
            msg['Subject'] = f"[Syslog Server] {alert['level'].upper()} Alert: {alert['type']}"
            
            body = f"""
            Alert Type: {alert['type']}
            Level: {alert['level']}
            Message: {alert['message']}
            Time: {alert['timestamp']}
            
            Details:
            {alert['details']}
            """
            msg.attach(MIMEText(body, 'plain'))
            
            with smtplib.SMTP(email_config['smtp_server'], email_config['smtp_port']) as server:
                server.starttls()
                server.login(email_config['username'], email_config['password'])
                server.send_message(msg)
            
            return True
        except Exception as e:
            print(f"Email alert failed: {e}")
            return False
    
    def _check_disk_space(self):
        try:
            import os
            statvfs = os.statvfs(os.path.dirname(Config.DATABASE_PATH))
            total_space = statvfs.f_frsize * statvfs.f_blocks
            free_space = statvfs.f_frsize * statvfs.f_bavail
            used_percent = ((total_space - free_space) / total_space) * 100
            
            if used_percent >= Config.ALERT_RULES['disk_space']['threshold_percent']:
                self.send_alert(
                    'disk_space',
                    f"磁盘空间使用率达到 {used_percent:.1f}%，超过阈值 {Config.ALERT_RULES['disk_space']['threshold_percent']}%",
                    'critical',
                    {
                        'total_space_gb': total_space / 1024 / 1024 / 1024,
                        'free_space_gb': free_space / 1024 / 1024 / 1024,
                        'used_percent': used_percent
                    }
                )
        except Exception as e:
            print(f"Disk space check failed: {e}")
    
    def check_high_severity(self, severity_counts, time_window_minutes=5):
        rule = Config.ALERT_RULES.get('high_severity')
        if not rule or not rule.get('enabled'):
            return
        
        total_high = sum(severity_counts.get(s, 0) for s in rule.get('severities', []))
        if total_high >= rule.get('threshold', 5):
            self.send_alert(
                'high_severity',
                f"在最近 {time_window_minutes} 分钟内收到 {total_high} 条高严重性日志",
                'critical',
                {
                    'severity_counts': severity_counts,
                    'threshold': rule['threshold']
                }
            )
    
    def check_anomaly_rate(self, rate_per_second):
        rule = Config.ALERT_RULES.get('anomaly_rate')
        if not rule or not rule.get('enabled'):
            return
        
        if rate_per_second >= rule.get('threshold', 100):
            self.send_alert(
                'anomaly_rate',
                f"日志接收速率异常: {rate_per_second:.1f} 条/秒，超过阈值 {rule['threshold']} 条/秒",
                'warning',
                {
                    'current_rate': rate_per_second,
                    'threshold': rule['threshold']
                }
            )
    
    def check_integrity_failure(self, integrity_result):
        rule = Config.ALERT_RULES.get('integrity_failure')
        if not rule or not rule.get('enabled'):
            return
        
        if not integrity_result.get('valid', True):
            self.send_alert(
                'integrity_failure',
                f"日志完整性校验失败: {integrity_result.get('mismatches', 0)} 条记录不匹配",
                'critical',
                integrity_result
            )
    
    def get_alert_info(self):
        return {
            'enabled': Config.ALERT_ENABLED,
            'webhook_configured': self.get_webhook_url() != '',
            'email_configured': self.is_email_enabled(),
            'rules': Config.ALERT_RULES,
            'recent_alerts': self.alert_history[-10:]
        }
    
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)


_alert_manager = None

def get_alert_manager():
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = AlertManager()
    return _alert_manager

def start_alert(db=None):
    manager = get_alert_manager()
    if db:
        manager.db = db
        manager._load_config()
    manager.start()
    return manager