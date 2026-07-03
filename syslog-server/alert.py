import requests
import threading
import time
from datetime import datetime
from config import Config

class AlertManager:
    def __init__(self):
        self.running = False
        self.thread = None
        self.alert_history = []
        self.last_alerts = {}
    
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
        if Config.ALERT_WEBHOOK_URL:
            sent |= self._send_webhook(alert)
        
        if Config.ALERT_EMAIL_ENABLED:
            sent |= self._send_email(alert)
        
        return sent
    
    def _send_webhook(self, alert):
        try:
            payload = {
                'alert': alert,
                'timestamp': alert['timestamp']
            }
            response = requests.post(
                Config.ALERT_WEBHOOK_URL,
                json=payload,
                timeout=10
            )
            return response.status_code == 200
        except Exception as e:
            print(f"Webhook alert failed: {e}")
            return False
    
    def _send_email(self, alert):
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            
            msg = MIMEMultipart()
            msg['From'] = Config.ALERT_EMAIL_SENDER
            msg['To'] = Config.ALERT_EMAIL_RECIPIENT
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
            
            with smtplib.SMTP(Config.ALERT_EMAIL_SMTP_SERVER, Config.ALERT_EMAIL_SMTP_PORT) as server:
                server.starttls()
                server.login(Config.ALERT_EMAIL_USERNAME, Config.ALERT_EMAIL_PASSWORD)
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
            'webhook_configured': Config.ALERT_WEBHOOK_URL is not None,
            'email_configured': Config.ALERT_EMAIL_ENABLED,
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

def start_alert():
    manager = get_alert_manager()
    manager.start()
    return manager