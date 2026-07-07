import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

class Config:
    VERSION = '1.1.1'
    BUILD_DATE = '2026-07-07'
    SYSLOG_UDP_PORT = 5140
    SYSLOG_TCP_PORT = 5140
    SYSLOG_HOST = '0.0.0.0'
    
    DATABASE_PATH = os.path.join(BASE_DIR, 'syslog.db')
    
    WEB_HOST = '0.0.0.0'
    WEB_PORT = 5000
    DEBUG = False
    
    LOG_QUEUE_MAXSIZE = 10000
    
    MAX_LOG_AGE_DAYS = 180

    NTP_SERVERS = ['pool.ntp.org', 'time.nist.gov']

    BACKUP_DIR = os.path.join(BASE_DIR, 'backups')
    BACKUP_INTERVAL_HOURS = 24
    BACKUP_RETENTION_DAYS = 30

    AUTH_ENABLED = True
    ADMIN_USERNAME = 'admin'
    ADMIN_PASSWORD = 'syslog@2024'
    SESSION_SECRET_KEY = 'syslog-server-secret-key-change-in-production'
    SESSION_TIMEOUT = 3600
    LOGIN_MAX_ATTEMPTS = 5
    LOGIN_BAN_DURATION = 300

    ALERT_ENABLED = True
    ALERT_WEBHOOK_URL = None
    ALERT_EMAIL_ENABLED = False
    ALERT_EMAIL_SMTP_SERVER = None
    ALERT_EMAIL_SMTP_PORT = 587
    ALERT_EMAIL_SENDER = None
    ALERT_EMAIL_RECIPIENT = None
    ALERT_EMAIL_USERNAME = None
    ALERT_EMAIL_PASSWORD = None

    ALERT_RULES = {
        'high_severity': {
            'name': '高严重性日志',
            'enabled': True,
            'severities': [0, 1, 2],
            'threshold': 5,
            'time_window_minutes': 5
        },
        'anomaly_rate': {
            'name': '异常日志速率',
            'enabled': True,
            'threshold': 100,
            'time_window_minutes': 1
        },
        'integrity_failure': {
            'name': '日志完整性失败',
            'enabled': True
        },
        'disk_space': {
            'name': '磁盘空间告警',
            'enabled': True,
            'threshold_percent': 90
        }
    }
    
    FACILITY_MAP = {
        0: 'kern',
        1: 'user',
        2: 'mail',
        3: 'daemon',
        4: 'auth',
        5: 'syslog',
        6: 'lpr',
        7: 'news',
        8: 'uucp',
        9: 'cron',
        10: 'authpriv',
        11: 'ftp',
        12: 'ntp',
        13: 'security',
        14: 'console',
        15: 'solaris-cron',
        16: 'local0',
        17: 'local1',
        18: 'local2',
        19: 'local3',
        20: 'local4',
        21: 'local5',
        22: 'local6',
        23: 'local7'
    }
    
    SEVERITY_MAP = {
        0: 'emerg',
        1: 'alert',
        2: 'crit',
        3: 'err',
        4: 'warning',
        5: 'notice',
        6: 'info',
        7: 'debug'
    }
    
    SEVERITY_COLORS = {
        0: '#dc3545',
        1: '#dc3545',
        2: '#dc3545',
        3: '#fd7e14',
        4: '#ffc107',
        5: '#17a2b8',
        6: '#28a745',
        7: '#6c757d'
    }
