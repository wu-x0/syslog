"""
厂商日志识别模块
自动识别不同厂商/设备的日志格式
"""
import re
from typing import Optional, Dict, Tuple


class VendorDetector:
    """厂商检测器 - 根据日志特征识别设备厂商"""

    # 厂商信息配置
    VENDOR_INFO = {
        'huawei': {
            'name': '华为',
            'icon': '🔷',
            'color': '#E60012',
            'patterns': [
                r'%\w+[\-_]\d+/\d+/\d+',  # 华为VRP格式: %SYSLOG_1/1/1
                r'VRP',
                r'HUAWEI',
                r'Switch\s*\(Config\)',
                r'\[HUawei\]',
                r' Huawei ',
            ],
            'keywords': ['VRP', 'HUAWEI', 'Huawei', 'S-series', 'CE', 'AR', 'USG']
        },
        'h3c': {
            'name': 'H3C/新华三',
            'icon': '🟢',
            'color': '#00A854',
            'patterns': [
                r'%\w+[\-_]SLOT\d+',  # H3C格式
                r'Comware',
                r'H3C',
                r'\[H3C\]',
                r'H3C\s+S\d+',
                r'Unit\s+\d+',
            ],
            'keywords': ['H3C', 'Comware', 'S5120', 'S5500', 'S7500', 'S12500', 'CAS', 'UIS']
        },
        'cisco': {
            'name': '思科',
            'icon': '🟡',
            'color': '#00BCEB',
            'patterns': [
                r'%\w+-\d+-\w+',  # Cisco IOS格式: %SYS-5-CONFIG_I
                r'%\w+-M-\w+',    # Cisco NX-OS格式
                r'Cisco\s+IOS',
                r'Cisco\s+NX-OS',
                r'\[cisco\]',
            ],
            'keywords': ['Cisco', 'IOS', 'NX-OS', 'ASA', 'Catalyst', 'Nexus', 'Router', 'Switch']
        },
        'juniper': {
            'name': 'Juniper',
            'icon': '🟠',
            'color': '#FF6B00',
            'patterns': [
                r'Junos',
                r'JUNOS',
                r'\[junos\]',
                r'chassisd',
                r'rpd',
                r'mib2d',
                r'snmpd',
            ],
            'keywords': ['Juniper', 'Junos', 'JUNOS', 'SRX', 'MX', 'EX', 'PTX']
        },
        'arista': {
            'name': 'Arista',
            'icon': '🔴',
            'color': '#FF4F4F',
            'patterns': [
                r'Arista',
                r'EOS',
                r'\[Arista\]',
            ],
            'keywords': ['Arista', 'EOS', 'DCS']
        },
        'linux': {
            'name': 'Linux',
            'icon': '🐧',
            'color': '#FCC624',
            'patterns': [
                r'systemd',
                r'sshd',
                r'kernel:',
                r'syslog',
                r'CRON',
                r'nginx',
                r'apache',
                r'mysql',
                r'postfix',
                r'dovecot',
            ],
            'keywords': ['systemd', 'ssh', 'kernel', 'Ubuntu', 'CentOS', 'Debian', 'RedHat']
        },
        'windows': {
            'name': 'Windows',
            'icon': '🪟',
            'color': '#0078D4',
            'patterns': [
                r'Microsoft',
                r'Windows',
                r'EventID',
                r'Security-Auditing',
                r'Microsoft-Windows',
            ],
            'keywords': ['Windows', 'Microsoft', 'PowerShell', 'IIS', 'Active Directory']
        },
        'aliyun': {
            'name': '阿里云',
            'icon': '☁️',
            'color': '#FF6A00',
            'patterns': [
                r'aliyun',
                r'Alibaba',
                r'ACS',
                r'ECS',
                r'SLB',
                r'RDS',
                r'\[aliyun\]',
            ],
            'keywords': ['aliyun', 'Alibaba', 'ECS', 'OSS', 'RDS', 'SLB', 'ACK']
        },
        'tencent': {
            'name': '腾讯云',
            'icon': '☁️',
            'color': '#00A3FF',
            'patterns': [
                r'tencent',
                r'TencentCloud',
                r'Tencent',
                r'CVM',
                r'CLB',
                r'\[tencent\]',
            ],
            'keywords': ['tencent', 'TencentCloud', 'CVM', 'COS', 'CLB', 'TKE']
        },
        'aws': {
            'name': 'AWS',
            'icon': '☁️',
            'color': '#FF9900',
            'patterns': [
                r'AWS',
                r'Amazon',
                r'EC2',
                r'S3',
                r'CloudWatch',
                r'Lambda',
                r'\[aws\]',
            ],
            'keywords': ['AWS', 'Amazon', 'EC2', 'S3', 'RDS', 'Lambda', 'CloudWatch']
        },
        'vmware': {
            'name': 'VMware',
            'icon': '🖥️',
            'color': '#607078',
            'patterns': [
                r'VMware',
                r'ESXi',
                r'vCenter',
                r'vSphere',
                r'VMkernel',
            ],
            'keywords': ['VMware', 'ESXi', 'vCenter', 'vSphere', 'VMkernel']
        },
        'fortinet': {
            'name': 'Fortinet',
            'icon': '🔒',
            'color': '#DA121A',
            'patterns': [
                r'FortiGate',
                r'FortiAnalyzer',
                r'FortiManager',
                r'Fortinet',
                r'FGT',
            ],
            'keywords': ['FortiGate', 'Fortinet', 'FortiAnalyzer', 'FortiManager', 'FGT']
        },
        'paloalto': {
            'name': 'Palo Alto',
            'icon': '🔒',
            'color': '#F05A28',
            'patterns': [
                r'PAN-OS',
                r'Palo Alto',
                r'PA-',
                r'Panorama',
            ],
            'keywords': ['PAN-OS', 'Palo Alto', 'Panorama', 'PA-']
        },
        'checkpoint': {
            'name': 'Check Point',
            'icon': '🔒',
            'color': '#E60012',
            'patterns': [
                r'Check Point',
                r'CP',
                r'FireWall-1',
                r'SmartCenter',
            ],
            'keywords': ['Check Point', 'CP', 'FireWall-1', 'SmartCenter']
        },
        'f5': {
            'name': 'F5 Networks',
            'icon': '🌐',
            'color': '#E31937',
            'patterns': [
                r'BIG-IP',
                r'F5',
                r'LTM',
                r'ASM',
                r'APM',
            ],
            'keywords': ['BIG-IP', 'F5', 'LTM', 'ASM', 'APM', 'iRules']
        },
        'dell': {
            'name': 'Dell EMC',
            'icon': '💻',
            'color': '#007DB8',
            'patterns': [
                r'Dell',
                r'EMC',
                r'PowerEdge',
                r'iDRAC',
            ],
            'keywords': ['Dell', 'EMC', 'PowerEdge', 'iDRAC', 'PowerStore']
        },
        'hp': {
            'name': 'HP/HPE',
            'icon': '💻',
            'color': '#0096D6',
            'patterns': [
                r'HP',
                r'HPE',
                r'ProCurve',
                r'ProLiant',
                r'iLO',
            ],
            'keywords': ['HP', 'HPE', 'ProCurve', 'ProLiant', 'iLO', 'Comware']
        },
        'synology': {
            'name': 'Synology',
            'icon': '💾',
            'color': '#B5D56A',
            'patterns': [
                r'Synology',
                r'DiskStation',
                r'DSM',
            ],
            'keywords': ['Synology', 'DiskStation', 'DSM', 'RS', 'DS']
        },
        'ubiquiti': {
            'name': 'Ubiquiti',
            'icon': '📶',
            'color': '#0559C9',
            'patterns': [
                r'Ubiquiti',
                r'UniFi',
                r'EdgeRouter',
                r'USG',
                r'UAP',
            ],
            'keywords': ['Ubiquiti', 'UniFi', 'EdgeRouter', 'USG', 'UAP', 'USW']
        },
        'zyxel': {
            'name': 'ZyXEL',
            'icon': '📡',
            'color': '#7B68EE',
            'patterns': [
                r'ZyXEL',
                r'ZyWall',
                r'USG',
            ],
            'keywords': ['ZyXEL', 'ZyWall', 'USG', 'GS']
        },
        'sonicwall': {
            'name': 'SonicWall',
            'icon': '🔒',
            'color': '#FF7200',
            'patterns': [
                r'SonicWall',
                r'SonicOS',
                r'SW',
            ],
            'keywords': ['SonicWall', 'SonicOS', 'SW']
        },
        'ruckus': {
            'name': 'Ruckus',
            'icon': '📶',
            'color': '#FF7F00',
            'patterns': [
                r'Ruckus',
                r'ZoneDirector',
                r'SmartZone',
                r'ICX',
            ],
            'keywords': ['Ruckus', 'ZoneDirector', 'SmartZone', 'ICX', 'R720']
        },
        'extreme': {
            'name': 'Extreme Networks',
            'icon': '🔀',
            'color': '#6A1B9A',
            'patterns': [
                r'Extreme',
                r'XOS',
                r'Summit',
                r'BlackDiamond',
            ],
            'keywords': ['Extreme', 'XOS', 'Summit', 'BlackDiamond', 'EXOS']
        },
        'brocade': {
            'name': 'Brocade',
            'icon': '🔀',
            'color': '#0097A7',
            'patterns': [
                r'Brocade',
                r'Fabric\s+OS',
                r'ICX',
                r'VDX',
            ],
            'keywords': ['Brocade', 'Fabric OS', 'ICX', 'VDX']
        },
        'huawei_cloud': {
            'name': '华为云',
            'icon': '☁️',
            'color': '#CF0A2C',
            'patterns': [
                r'Huawei\s+Cloud',
                r'HWS',
                r'ECS',
                r'OBS',
                r'huaweicloud',
            ],
            'keywords': ['华为云', 'Huawei Cloud', 'HWS', 'ECS', 'OBS']
        },
        'oracle': {
            'name': 'Oracle',
            'icon': '🔴',
            'color': '#F80000',
            'patterns': [
                r'Oracle',
                r'ORACLE',
                r'ORA-',
                r'Oracle\s+Database',
            ],
            'keywords': ['Oracle', 'ORA-', 'Oracle Database', 'Exadata']
        },
        'ibm': {
            'name': 'IBM',
            'icon': '🔵',
            'color': '#054ADA',
            'patterns': [
                r'IBM',
                r'AIX',
                r'IBM\s+i',
                r'WebSphere',
                r'DB2',
            ],
            'keywords': ['IBM', 'AIX', 'WebSphere', 'DB2', 'Power Systems']
        },
        'splunk': {
            'name': 'Splunk',
            'icon': '🦓',
            'color': '#67C92D',
            'patterns': [
                r'Splunk',
                r'splunkd',
                r'SplunkForwarder',
            ],
            'keywords': ['Splunk', 'splunkd', 'SplunkForwarder', 'Splunk Enterprise']
        },
        'nutanix': {
            'name': 'Nutanix',
            'icon': '☁️',
            'color': '#0067B3',
            'patterns': [
                r'Nutanix',
                r'AHV',
                r'Prism',
                r'AOS',
            ],
            'keywords': ['Nutanix', 'AHV', 'Prism', 'AOS']
        },
        'netapp': {
            'name': 'NetApp',
            'icon': '💾',
            'color': '#0067C5',
            'patterns': [
                r'NetApp',
                r'Data\s+ONTAP',
                r'ONTAP',
                r'clustered',
            ],
            'keywords': ['NetApp', 'ONTAP', 'Data ONTAP', 'FAS']
        },
        'other': {
            'name': '其他',
            'icon': '❓',
            'color': '#888888',
            'patterns': [],
            'keywords': []
        }
    }

    def __init__(self):
        # 预编译正则表达式以提高性能
        self._compiled_patterns = {}
        for vendor, info in self.VENDOR_INFO.items():
            if vendor == 'other':
                continue
            self._compiled_patterns[vendor] = [
                re.compile(pattern, re.IGNORECASE) for pattern in info['patterns']
            ]

    def detect(self, message: str, hostname: str = '', app_name: str = '') -> Tuple[str, Dict]:
        """
        检测日志的厂商来源

        Args:
            message: 日志消息内容
            hostname: 主机名
            app_name: 应用名称

        Returns:
            (vendor_id, vendor_info): 厂商ID和厂商信息字典
        """
        if not message:
            return 'other', self.VENDOR_INFO['other']

        # 检测优先级顺序
        detection_order = [
            'cisco', 'huawei', 'h3c', 'juniper', 'arista',
            'fortinet', 'paloalto', 'checkpoint', 'f5',
            'aliyun', 'tencent', 'aws', 'huawei_cloud',
            'vmware', 'nutanix', 'netapp',
            'dell', 'hp', 'synology',
            'ubiquiti', 'zyxel', 'sonicwall', 'ruckus', 'extreme', 'brocade',
            'oracle', 'ibm', 'splunk',
            'windows', 'linux',
            'other'
        ]

        # 组合检测文本
        detect_text = f"{hostname} {app_name} {message}".strip()

        # 按优先级顺序检测
        for vendor in detection_order:
            if vendor == 'other':
                continue

            info = self.VENDOR_INFO.get(vendor)
            if not info:
                continue

            # 检查正则模式
            patterns = self._compiled_patterns.get(vendor, [])
            for pattern in patterns:
                if pattern.search(detect_text):
                    return vendor, info

            # 检查关键词
            for keyword in info['keywords']:
                if keyword.lower() in detect_text.lower():
                    return vendor, info

        # 默认返回 'other'
        return 'other', self.VENDOR_INFO['other']

    def get_vendor_name(self, vendor_id: str) -> str:
        """获取厂商显示名称"""
        info = self.VENDOR_INFO.get(vendor_id, self.VENDOR_INFO['other'])
        return info['name']

    def get_vendor_icon(self, vendor_id: str) -> str:
        """获取厂商图标"""
        info = self.VENDOR_INFO.get(vendor_id, self.VENDOR_INFO['other'])
        return info['icon']

    def get_vendor_color(self, vendor_id: str) -> str:
        """获取厂商显示颜色"""
        info = self.VENDOR_INFO.get(vendor_id, self.VENDOR_INFO['other'])
        return info['color']

    def get_all_vendors(self) -> Dict:
        """获取所有厂商信息"""
        return self.VENDOR_INFO.copy()


# 全局检测器实例
_detector = None


def get_detector() -> VendorDetector:
    """获取全局检测器实例"""
    global _detector
    if _detector is None:
        _detector = VendorDetector()
    return _detector


def detect_vendor(message: str, hostname: str = '', app_name: str = '') -> Tuple[str, Dict]:
    """
    检测厂商的便捷函数

    Args:
        message: 日志消息内容
        hostname: 主机名
        app_name: 应用名称

    Returns:
        (vendor_id, vendor_info): 厂商ID和厂商信息字典
    """
    return get_detector().detect(message, hostname, app_name)