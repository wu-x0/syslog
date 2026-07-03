import sqlite3
import threading
import queue
import time
import hashlib
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
                vendor_name TEXT,
                checksum TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS integrity_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_time TEXT NOT NULL,
                total_records INTEGER NOT NULL,
                total_hash TEXT NOT NULL
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trusted_hosts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hostname TEXT,
                ip_address TEXT,
                description TEXT,
                enabled INTEGER DEFAULT 1,
                created_at TEXT,
                updated_at TEXT
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS static_routes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                destination TEXT NOT NULL,
                gateway TEXT NOT NULL,
                metric INTEGER DEFAULT 100,
                enabled INTEGER DEFAULT 1,
                created_at TEXT,
                updated_at TEXT
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

    def _compute_checksum(self, log_data):
        data_str = f"{log_data.get('received_at', '')}|{log_data.get('timestamp', '')}|{log_data.get('facility', '')}|{log_data.get('severity', '')}|{log_data.get('hostname', '')}|{log_data.get('source_ip', '')}|{log_data.get('app_name', '')}|{log_data.get('message', '')}|{log_data.get('raw_message', '')}"
        return hashlib.sha256(data_str.encode()).hexdigest()
    
    def insert_log(self, log_data):
        conn = self._get_conn()
        cursor = conn.cursor()
        checksum = self._compute_checksum(log_data)
        cursor.execute('''
            INSERT INTO syslogs (
                received_at, timestamp, facility, facility_str, severity,
                severity_str, hostname, source_ip, app_name, proc_id,
                message, raw_message, vendor, vendor_name, checksum
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            log_data.get('vendor_name', '其他'),
            checksum
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
                message, raw_message, vendor, vendor_name, checksum
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            log.get('vendor_name', '其他'),
            self._compute_checksum(log)
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

    def verify_integrity(self):
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute('SELECT id, received_at, timestamp, facility, severity, hostname, source_ip, app_name, message, raw_message, checksum FROM syslogs ORDER BY id')
        rows = cursor.fetchall()
        
        mismatches = 0
        missing_checksum = 0
        
        for row in rows:
            if not row['checksum']:
                missing_checksum += 1
                continue
            
            log_dict = {
                'received_at': row['received_at'],
                'timestamp': row['timestamp'],
                'facility': row['facility'],
                'severity': row['severity'],
                'hostname': row['hostname'],
                'source_ip': row['source_ip'],
                'app_name': row['app_name'],
                'message': row['message'],
                'raw_message': row['raw_message']
            }
            computed_checksum = self._compute_checksum(log_dict)
            if computed_checksum != row['checksum']:
                mismatches += 1
        
        valid = mismatches == 0
        
        return {
            'total_records': len(rows),
            'mismatches': mismatches,
            'missing_checksum': missing_checksum,
            'valid': valid
        }

    def create_integrity_snapshot(self):
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute('SELECT checksum FROM syslogs ORDER BY id')
        rows = cursor.fetchall()
        
        total_hash = hashlib.sha256()
        for row in rows:
            total_hash.update(row['checksum'].encode())
        
        total_hash_str = total_hash.hexdigest()
        
        cursor.execute('''
            INSERT INTO integrity_snapshots (snapshot_time, total_records, total_hash)
            VALUES (?, ?, ?)
        ''', (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), len(rows), total_hash_str))
        conn.commit()
        
        return {
            'snapshot_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'total_records': len(rows),
            'total_hash': total_hash_str
        }

    def get_integrity_snapshots(self, limit=10):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM integrity_snapshots ORDER BY id DESC LIMIT ?', (limit,))
        return [dict(row) for row in cursor.fetchall()]

    def get_setting(self, key, default=None):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
        row = cursor.fetchone()
        if row and row['value'] is not None:
            value = row['value']
            if isinstance(default, bool):
                return value.lower() == 'true'
            if isinstance(default, int):
                try:
                    return int(value)
                except ValueError:
                    return default
            return value
        return default

    def set_setting(self, key, value):
        conn = self._get_conn()
        cursor = conn.cursor()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('''
            INSERT INTO settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        ''', (key, str(value), now))
        conn.commit()

    def get_all_settings(self):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('SELECT key, value FROM settings')
        return {row['key']: row['value'] for row in cursor.fetchall()}

    def get_trusted_hosts(self):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM trusted_hosts ORDER BY id')
        return [dict(row) for row in cursor.fetchall()]

    def add_trusted_host(self, hostname=None, ip_address=None, description=''):
        conn = self._get_conn()
        cursor = conn.cursor()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('''
            INSERT INTO trusted_hosts (hostname, ip_address, description, enabled, created_at, updated_at)
            VALUES (?, ?, ?, 1, ?, ?)
        ''', (hostname, ip_address, description, now, now))
        conn.commit()
        return cursor.lastrowid

    def update_trusted_host(self, host_id, hostname=None, ip_address=None, description=None, enabled=None):
        conn = self._get_conn()
        cursor = conn.cursor()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        fields = []
        values = []
        if hostname is not None:
            fields.append('hostname = ?')
            values.append(hostname)
        if ip_address is not None:
            fields.append('ip_address = ?')
            values.append(ip_address)
        if description is not None:
            fields.append('description = ?')
            values.append(description)
        if enabled is not None:
            fields.append('enabled = ?')
            values.append(1 if enabled else 0)
        if not fields:
            return False
        fields.append('updated_at = ?')
        values.append(now)
        values.append(host_id)
        cursor.execute(f'UPDATE trusted_hosts SET {", ".join(fields)} WHERE id = ?', values)
        conn.commit()
        return cursor.rowcount > 0

    def delete_trusted_host(self, host_id):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM trusted_hosts WHERE id = ?', (host_id,))
        conn.commit()
        return cursor.rowcount > 0

    def is_trusted_host(self, ip_address=None, hostname=None):
        trusted = self.get_trusted_hosts()
        enabled_hosts = [h for h in trusted if h['enabled'] == 1]
        
        if not enabled_hosts:
            return True
        
        for host in enabled_hosts:
            if ip_address and host['ip_address'] and host['ip_address'] == ip_address:
                return True
            if hostname and host['hostname'] and host['hostname'] == hostname:
                return True
        
        return False

    def get_static_routes(self):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM static_routes ORDER BY id')
        return [dict(row) for row in cursor.fetchall()]

    def add_static_route(self, destination, gateway, metric=100):
        conn = self._get_conn()
        cursor = conn.cursor()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('''
            INSERT INTO static_routes (destination, gateway, metric, enabled, created_at, updated_at)
            VALUES (?, ?, ?, 1, ?, ?)
        ''', (destination, gateway, metric, now, now))
        conn.commit()
        return cursor.lastrowid

    def update_static_route(self, route_id, destination=None, gateway=None, metric=None, enabled=None):
        conn = self._get_conn()
        cursor = conn.cursor()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        fields = []
        values = []
        if destination is not None:
            fields.append('destination = ?')
            values.append(destination)
        if gateway is not None:
            fields.append('gateway = ?')
            values.append(gateway)
        if metric is not None:
            fields.append('metric = ?')
            values.append(metric)
        if enabled is not None:
            fields.append('enabled = ?')
            values.append(1 if enabled else 0)
        
        if not fields:
            return False
        
        fields.append('updated_at = ?')
        values.append(now)
        values.append(route_id)
        
        cursor.execute(f"UPDATE static_routes SET {', '.join(fields)} WHERE id = ?", values)
        conn.commit()
        return cursor.rowcount > 0

    def delete_static_route(self, route_id):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM static_routes WHERE id = ?', (route_id,))
        conn.commit()
        return cursor.rowcount > 0

    def get_enabled_static_routes(self):
        routes = self.get_static_routes()
        return [r for r in routes if r['enabled'] == 1]


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
                    try:
                        from web.api import record_log_received
                        record_log_received(len(batch))
                    except Exception:
                        pass
                    batch = []
                    last_flush = time.time()
            except queue.Empty:
                if batch:
                    self.db.insert_many_logs(batch)
                    try:
                        from web.api import record_log_received
                        record_log_received(len(batch))
                    except Exception:
                        pass
                    batch = []
                    last_flush = time.time()
    
    def stop(self):
        self.running = False
        self.join(timeout=2)
