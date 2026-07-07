#!/bin/bash
set -e

echo "======================================"
echo "  Syslog 日志服务器 部署脚本"
echo "======================================"

INSTALL_DIR="/opt/syslog-server"

echo ""
echo "[1/6] 更新系统并安装依赖..."
apt-get update && apt-get install -y python3 python3-pip python3-venv git

echo ""
echo "[2/6] 创建项目目录..."
mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

echo ""
echo "[3/6] 获取项目代码..."
if [ -f "app.py" ]; then
    echo "项目文件已存在，跳过下载"
elif [ -d .git ]; then
    echo "执行 git pull 更新..."
    git pull origin main || echo "更新失败，使用现有文件"
else
    echo "从 GitHub 克隆..."
    git clone https://github.com/wu-x0/syslog.git /tmp/syslog-tmp || {
        echo "GitHub 访问失败！请手动上传项目文件到 $INSTALL_DIR"
        exit 1
    }
    # 仓库根目录是 /workspace，项目在 syslog-server/ 子目录
    if [ -d "/tmp/syslog-tmp/syslog-server" ]; then
        cp -a /tmp/syslog-tmp/syslog-server/. "$INSTALL_DIR/"
        cp -a /tmp/syslog-tmp/.git "$INSTALL_DIR/" 2>/dev/null || true
    else
        cp -a /tmp/syslog-tmp/. "$INSTALL_DIR/"
    fi
    rm -rf /tmp/syslog-tmp
fi

echo ""
echo "[4/6] 创建虚拟环境..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip
pip install flask requests netifaces

echo ""
echo "[5/6] 创建 systemd 服务..."
cat > /etc/systemd/system/syslog-server.service << EOF
[Unit]
Description=Syslog Server
After=network.target

[Service]
User=root
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python3 app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable syslog-server

echo ""
echo "[6/6] 启动服务..."
systemctl restart syslog-server

echo ""
echo "======================================"
echo "  部署完成！"
echo "======================================"
echo ""
echo "服务状态:"
systemctl status syslog-server --no-pager | head -15
echo ""
echo "Web 界面: http://\$(hostname -I | awk '{print \$1}'):5000"
echo "Syslog 端口: 5140 (UDP/TCP)"
echo ""
echo "常用命令:"
echo "  启动: systemctl start syslog-server"
echo "  停止: systemctl stop syslog-server"
echo "  重启: systemctl restart syslog-server"
echo "  状态: systemctl status syslog-server"
echo "  日志: journalctl -u syslog-server -f"
echo ""
echo "更新代码: bash $INSTALL_DIR/update.sh"