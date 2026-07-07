#!/bin/bash
set -e

echo "======================================"
echo "  Syslog 日志服务器 离线部署脚本"
echo "======================================"

cd "$(dirname "$0")"

echo ""
echo "[1/4] 安装系统依赖..."
apt-get update && apt-get install -y python3 python3-pip python3-venv

echo ""
echo "[2/4] 创建虚拟环境..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install flask requests

echo ""
echo "[3/4] 创建 systemd 服务..."
cat > /etc/systemd/system/syslog-server.service << 'EOF'
[Unit]
Description=Syslog Server
After=network.target

[Service]
User=root
WorkingDirectory=/opt/syslog-server
ExecStart=/opt/syslog-server/venv/bin/python3 app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable syslog-server
systemctl start syslog-server

echo ""
echo "======================================"
echo "  部署完成！"
echo "======================================"
echo ""
echo "服务状态:"
systemctl status syslog-server --no-pager
echo ""
echo "Web 界面: http://<服务器IP>:5000"
echo "Syslog 端口: 5140 (UDP/TCP)"
echo ""
echo "常用命令:"
echo "  启动: systemctl start syslog-server"
echo "  停止: systemctl stop syslog-server"
echo "  重启: systemctl restart syslog-server"
echo "  日志: journalctl -u syslog-server -f"