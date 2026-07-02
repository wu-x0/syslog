import sqlite3
import threading
import queue
import time
from datetime import datetime, timedelta
from config import Config

class Database:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, db_path=None):
        if hasattr(self, 'initialized'):
            return
        self.db_path = db_path or Config.DATABASE_PATH
        self.local = threading.local()
        self._init_db()
        self.initialized = True
    
    def _get_conn(self):
        if not hasattr(self.local, 'conn') or self.local.conn is None:
            self.local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.local.conn.row_factory = sqlite3.Row
            self.local.conn.execute('PRAGMA journal_mode=WAL')
            self.local.conn.execute('PRAGMA synchronous=NORMAL')
        return self.local.conn
    
    def _init_db(self):
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS syslogs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                received_at TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                facility INTEGER NOT NULL,
                facility_str TEXT NOT NULL,
                severity INTEGER NOT NULL,
                severity_str TEXT NOT NULL,
                hostname TEXT,
                source_ip TEXT,
                app_name TEXT,
                proc_id TEXT,
                message TEXT,
                raw_message TEXT,
                vendor TEXT,
                vendor_name TEXT
            )
        ''')
        
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_syslogs_timestamp ON syslogs(timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_syslogs_severity ON syslogs(severity)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_syslogs_facility ON syslogs(facility)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_syslogs_hostname ON syslogs(hostname)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_syslogs_source_ip ON syslogs(source_ip)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_syslogs_app_name ON syslogs(app_name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_syslogs_vendor ON syslogs(vendor)')
        
        conn.commit()
    
    def insert_log(self, log_data):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO syslogs (
                received_at, timestamp, facility, facility_str, severity,
                severity_str, hostname, source_ip, app_name, proc_id,
                message, raw_message, vendor, vendor_name
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            log_data['received_at'],
            log_data['timestamp'],
            log_data['facility'],
            log_data['facility_str'],
            log_data['severity'],
            log_data['severity_str'],
            log_data['hostname'],
            log_data['source_ip'],
            log_data['app_name'],
            log_data['proc_id'],
            log_data['message'],
            log_data['raw_message'],
            log_data.get('vendor', 'other'),
            log_data.get('vendor_name', '其他')
        ))
        conn.commit()
        return cursor.lastrowid

    def insert_many_logs(self, logs_list):
        if not logs_list:
            return
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.executemany('''
            INSERT INTO syslogs (
                received_at, timestamp, facility, facility_str, severity,
                severity_str, hostname, source_ip, app_name, proc_id,
                message, raw_message, vendor, vendor_name
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', [(
            log['received_at'],
            log['timestamp'],
            log['facility'],
            log['facility_str'],
            log['severity'],
            log['severity_str'],
            log['hostname'],
            log['source_ip'],
            log['app_name'],
            log['proc_id'],
            log['message'],
            log['raw_message'],
            log.get('vendor', 'other'),
            log.get('vendor_name', '其他')
        ) for log in logs_list])
        conn.commit()
    
    def get_logs(self, page=1, per_page=50, severity=None, facility=None,
                 hostname=None, source_ip=None, app_name=None, vendor=None,
                 search=None, start_time=None, end_time=None,
                 order='desc'):
        conn = self._get_conn()
        cursor = conn.cursor()

        query = 'SELECT * FROM syslogs WHERE 1=1'
        params = []

        if severity is not None:
            query += ' AND severity = ?'
            params.append(severity)

        if facility is not None:
            query += ' AND facility = ?'
            params.append(facility)

        if hostname:
            query += ' AND hostname LIKE ?'
            params.append(f'%{hostname}%')

        if source_ip:
            query += ' AND source_ip LIKE ?'
            params.append(f'%{source_ip}%')

        if app_name:
            query += ' AND app_name LIKE ?'
            params.append(f'%{app_name}%')

        if vendor:
            query += ' AND vendor = ?'
            params.append(vendor)

        if search:
            query += ' AND (message LIKE ? OR raw_message LIKE ?)'
            params.extend([f'%{search}%', f'%{search}%'])

        if start_time:
            query += ' AND timestamp >= ?'
            params.append(start_time)

        if end_time:
            query += ' AND timestamp <= ?'
            params.append(end_time)
        
        count_query = query.replace('SELECT *', 'SELECT COUNT(*) as count', 1)
        cursor.execute(count_query, params)
        total = cursor.fetchone()['count']
        
        query += f' ORDER BY timestamp {order.upper()}, id {order.upper()}'
        query += ' LIMIT ? OFFSET ?'
        params.extend([per_page, (page - 1) * per_page])
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        logs = [dict(row) for row in rows]
        
        return {
            'logs': logs,
            'total': total,
            'page': page,
            'per_page': per_page,
            'total_pages': (total + per_page - 1) // per_page
        }
    
    def get_log_by_id(self, log_id):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM syslogs WHERE id = ?', (log_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    
    def get_statistics(self, hours=24):
        conn = self._get_conn()
        cursor = conn.cursor()
        
        since = (datetime.now() - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')
        
        cursor.execute('''
            SELECT severity, COUNT(*) as count
            FROM syslogs
            WHERE timestamp >= ?
            GROUP BY severity
            ORDER BY severity
        ''', (since,))
        severity_stats = {row['severity']: row['count'] for row in cursor.fetchall()}
        
        cursor.execute('''
            SELECT facility, COUNT(*) as count
            FROM syslogs
            WHERE timestamp >= ?
            GROUP BY facility
            ORDER BY count DESC
            LIMIT 10
        ''', (since,))
        facility_stats = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute('''
            SELECT hostname, COUNT(*) as count
            FROM syslogs
            WHERE timestamp >= ?
            GROUP BY hostname
            ORDER BY count DESC
            LIMIT 10
        ''', (since,))
        host_stats = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute('''
            SELECT app_name, COUNT(*) as count
            FROM syslogs
            WHERE timestamp >= ? AND app_name IS NOT NULL AND app_name != ''
            GROUP BY app_name
            ORDER BY count DESC
            LIMIT 10
        ''', (since,))
        app_stats = [dict(row) for row in cursor.fetchall()]

        cursor.execute('''
            SELECT vendor, vendor_name, COUNT(*) as count
            FROM syslogs
            WHERE timestamp >= ? AND vendor IS NOT NULL AND vendor != ''
            GROUP BY vendor, vendor_name
            ORDER BY count DESC
            LIMIT 10
        ''', (since,))
        vendor_stats = [dict(row) for row in cursor.fetchall()]

        cursor.execute('SELECT COUNT(*) as count FROM syslogs WHERE timestamp >= ?', (since,))
        total = cursor.fetchone()['count']
        
        time_format = '%Y-%m-%d %H:00:00'
        cursor.execute('''
            SELECT strftime('%Y-%m-%d %H:00:00', timestamp) as hour,
                   severity,
                   COUNT(*) as count
            FROM syslogs
            WHERE timestamp >= ?
            GROUP BY hour, severity
            ORDER BY hour
        ''', (since,))
        rows = cursor.fetchall()
        
        timeline_data = {}
        for row in rows:
            hour = row['hour']
            if hour not in timeline_data:
                timeline_data[hour] = {str(i): 0 for i in range(8)}
                timeline_data[hour]['total'] = 0
            timeline_data[hour][str(row['severity'])] = row['count']
            timeline_data[hour]['total'] += row['count']
        
        return {
            'total': total,
            'severity_stats': severity_stats,
            'facility_stats': facility_stats,
            'host_stats': host_stats,
            'app_stats': app_stats,
            'vendor_stats': vendor_stats,
            'timeline_data': timeline_data,
            'hours': hours
        }
    
    def get_recent_logs(self, limit=100):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM syslogs
            ORDER BY timestamp DESC, id DESC
            LIMIT ?
        ''', (limit,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    
    def get_distinct_values(self, column):
        valid_columns = ['hostname', 'source_ip', 'app_name', 'facility_str', 'severity_str', 'vendor', 'vendor_name']
        if column not in valid_columns:
            return []
        
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(f'SELECT DISTINCT {column} FROM syslogs WHERE {column} IS NOT NULL AND {column} != "" ORDER BY {column} LIMIT 100')
        rows = cursor.fetchall()
        return [row[0] for row in rows]
    
    def cleanup_old_logs(self, days=None):
        if days is None:
            days = Config.MAX_LOG_AGE_DAYS
        conn = self._get_conn()
        cursor = conn.cursor()
        cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('DELETE FROM syslogs WHERE timestamp < ?', (cutoff,))
        deleted = cursor.rowcount
        conn.commit()
        cursor.execute('VACUUM')
        return deleted
    
    def clear_all_logs(self):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM syslogs')
        conn.commit()
        cursor.execute('VACUUM')


class LogWriter(threading.Thread):
    def __init__(self, log_queue, db):
        super().__init__(daemon=True)
        self.log_queue = log_queue
        self.db = db
        self.running = True
        self.batch_size = 100
        self.batch_timeout = 0.5
    
    def run(self):
        batch = []
        last_flush = time.time()
        
        while self.running:
            try:
                log = self.log_queue.get(timeout=0.1)
                batch.append(log)
                
                if len(batch) >= self.batch_size or (time.time() - last_flush) > self.batch_timeout:
                    self.db.insert_many_logs(batch)
                    batch = []
                    last_flush = time.time()
            except queue.Empty:
                if batch:
                    self.db.insert_many_logs(batch)
                    batch = []
                    last_flush = time.time()
    
    def stop(self):
        self.running = False
        self.join(timeout=2)
