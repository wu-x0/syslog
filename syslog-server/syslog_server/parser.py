import re
import time
from datetime import datetime
from config import Config

RFC5424_REGEX = re.compile(
    r'^<(\d{1,3})>(\d+)\s+'
    r'(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?\s+'
    r'(\S+)\s+'
    r'(\S+)\s+'
    r'(\S+)\s+'
    r'(\S+)\s+'
    r'(?:\[.*?\]\s+)?'
    r'(.*)$'
)

BSD_SYSLOG_REGEX = re.compile(
    r'^<(\d{1,3})>'
    r'(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+'
    r'(\S+)\s+'
    r'(?:([^\s\[]+)(?:\[(\d+)\])?:\s)?'
    r'(.*)$'
)

def parse_priority(priority):
    priority = int(priority)
    facility = priority >> 3
    severity = priority & 0x07
    return facility, severity

def parse_syslog_message(message, source_ip):
    message = message.strip()
    if not message:
        return None
    
    facility = 1
    severity = 6
    timestamp = datetime.now()
    hostname = source_ip
    app_name = None
    proc_id = None
    msg_id = None
    msg = message
    version = None
    
    rfc_match = RFC5424_REGEX.match(message)
    if rfc_match:
        priority = rfc_match.group(1)
        facility, severity = parse_priority(priority)
        version = 'RFC5424'
        
        try:
            timestamp = datetime(
                int(rfc_match.group(3)),
                int(rfc_match.group(4)),
                int(rfc_match.group(5)),
                int(rfc_match.group(6)),
                int(rfc_match.group(7)),
                int(rfc_match.group(8))
            )
        except (ValueError, TypeError):
            timestamp = datetime.now()
        
        hostname = rfc_match.group(9)
        app_name = rfc_match.group(10)
        proc_id = rfc_match.group(11)
        msg_id = rfc_match.group(12)
        msg = rfc_match.group(13)
        
        if hostname == '-':
            hostname = source_ip
        if app_name == '-':
            app_name = None
        if proc_id == '-':
            proc_id = None
    else:
        bsd_match = BSD_SYSLOG_REGEX.match(message)
        if bsd_match:
            priority = bsd_match.group(1)
            facility, severity = parse_priority(priority)
            version = 'BSD'
            
            try:
                current_year = datetime.now().year
                time_str = f"{current_year} {bsd_match.group(2)}"
                timestamp = datetime.strptime(time_str, '%Y %b %d %H:%M:%S')
            except ValueError:
                timestamp = datetime.now()
            
            hostname = bsd_match.group(3)
            
            if bsd_match.group(4):
                app_name = bsd_match.group(4)
            
            if bsd_match.group(5):
                proc_id = bsd_match.group(5)
            
            if bsd_match.group(6):
                msg = bsd_match.group(6)
    
    facility_str = Config.FACILITY_MAP.get(facility, f'facility-{facility}')
    severity_str = Config.SEVERITY_MAP.get(severity, f'severity-{severity}')
    
    return {
        'received_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'timestamp': timestamp.strftime('%Y-%m-%d %H:%M:%S'),
        'facility': facility,
        'facility_str': facility_str,
        'severity': severity,
        'severity_str': severity_str,
        'hostname': hostname,
        'source_ip': source_ip,
        'app_name': app_name or '',
        'proc_id': proc_id or '',
        'message': msg,
        'raw_message': message
    }
