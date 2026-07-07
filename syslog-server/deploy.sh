#!/bin/bash
set -e

echo "======================================"
echo "  Syslog 日志服务器 一键部署脚本"
echo "======================================"

echo ""
echo "[1/5] 更新系统并安装依赖..."
apt-get update && apt-get install -y python3 python3-pip python3-venv git

echo ""
echo "[2/5] 创建项目目录..."
mkdir -p /opt/syslog-server
cd /opt/syslog-server

echo ""
echo "[3/5] 创建虚拟环境并安装依赖..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install flask requests

echo ""
echo "[4/5] 检查项目代码..."
if [ -f "app.py" ]; then
    echo "项目文件已存在，跳过下载"
else
    echo "尝试从 GitHub 下载..."
    if [ -d .git ]; then
        git pull origin main || echo "GitHub 访问失败，使用本地文件"
    else
        git clone https://github.com/wu-x0/syslog.git . || echo "GitHub 访问失败，请确保项目文件已上传"
    fi
fi

echo ""
echo "[5/5] 创建 systemd 服务..."
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
echo "日志查看: journalctl -u syslog-server -f"