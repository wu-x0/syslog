import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

class Config:
    SYSLOG_UDP_PORT = 5140
    SYSLOG_TCP_PORT = 5140
    SYSLOG_HOST = '0.0.0.0'
    
    DATABASE_PATH = os.path.join(BASE_DIR, 'syslog.db')
    
    WEB_HOST = '0.0.0.0'
    WEB_PORT = 5000
    DEBUG = False
    
    LOG_QUEUE_MAXSIZE = 10000
    
    MAX_LOG_AGE_DAYS = 30
    
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
