import os
import shutil
import time
import threading
from datetime import datetime, timedelta
from config import Config

class BackupManager:
    def __init__(self):
        self.backup_dir = Config.BACKUP_DIR
        self.interval_hours = Config.BACKUP_INTERVAL_HOURS
        self.retention_days = Config.BACKUP_RETENTION_DAYS
        self.running = False
        self.thread = None
        self.last_backup_time = 0
        self.backup_count = 0
        os.makedirs(self.backup_dir, exist_ok=True)
    
    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        print(f"Backup manager started, interval: {self.interval_hours}h, retention: {self.retention_days}d")
    
    def _run(self):
        while self.running:
            try:
                now = time.time()
                if now - self.last_backup_time >= self.interval_hours * 3600:
                    self.create_backup()
                time.sleep(3600)
            except Exception as e:
                print(f"Backup manager error: {e}")
    
    def create_backup(self):
        try:
            db_path = Config.DATABASE_PATH
            if not os.path.exists(db_path):
                return
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_name = f'syslog_backup_{timestamp}.db'
            backup_path = os.path.join(self.backup_dir, backup_name)
            
            shutil.copy2(db_path, backup_path)
            
            self.last_backup_time = time.time()
            self.backup_count += 1
            
            self._cleanup_old_backups()
            
            print(f"Backup created: {backup_name}")
            return backup_path
        except Exception as e:
            print(f"Backup failed: {e}")
            return None
    
    def _cleanup_old_backups(self):
        try:
            cutoff_time = time.time() - self.retention_days * 24 * 3600
            for filename in os.listdir(self.backup_dir):
                filepath = os.path.join(self.backup_dir, filename)
                if os.path.isfile(filepath):
                    mtime = os.path.getmtime(filepath)
                    if mtime < cutoff_time:
                        os.remove(filepath)
                        print(f"Removed old backup: {filename}")
        except Exception as e:
            print(f"Cleanup failed: {e}")
    
    def get_backup_info(self):
        backups = []
        try:
            for filename in sorted(os.listdir(self.backup_dir), reverse=True):
                filepath = os.path.join(self.backup_dir, filename)
                if os.path.isfile(filepath):
                    backups.append({
                        'filename': filename,
                        'size': os.path.getsize(filepath),
                        'modified': datetime.fromtimestamp(os.path.getmtime(filepath)).strftime('%Y-%m-%d %H:%M:%S')
                    })
        except Exception:
            pass
        
        return {
            'enabled': True,
            'interval_hours': self.interval_hours,
            'retention_days': self.retention_days,
            'last_backup': datetime.fromtimestamp(self.last_backup_time).strftime('%Y-%m-%d %H:%M:%S') if self.last_backup_time > 0 else 'Never',
            'backup_count': self.backup_count,
            'recent_backups': backups[:5]
        }
    
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)


_backup_manager = None

def get_backup_manager():
    global _backup_manager
    if _backup_manager is None:
        _backup_manager = BackupManager()
    return _backup_manager

def start_backup():
    manager = get_backup_manager()
    manager.start()
    return manager