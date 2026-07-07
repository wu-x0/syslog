#!/bin/bash
set -e

echo "======================================"
echo "  Syslog 日志服务器 更新脚本"
echo "======================================"

INSTALL_DIR="/opt/syslog-server"
cd "$INSTALL_DIR"

echo ""
echo "[1/4] 获取最新代码..."

if [ -d .git ]; then
    # 已有 git 仓库，直接 pull
    echo "执行 git pull..."
    git fetch origin main
    git reset --hard origin/main
elif [ -f "app.py" ]; then
    # 没有 git 仓库但有项目文件，重新克隆并覆盖
    echo "重新从 GitHub 克隆..."
    git clone https://github.com/wu-x0/syslog.git /tmp/syslog-update-tmp || {
        echo "GitHub 访问失败！请检查网络或手动上传文件"
        exit 1
    }
    # 仓库根目录是 /workspace，项目在 syslog-server/ 子目录
    if [ -d "/tmp/syslog-update-tmp/syslog-server" ]; then
        # 保留 venv 和数据库
        cp -a /tmp/syslog-update-tmp/syslog-server/. "$INSTALL_DIR/"
        cp -a /tmp/syslog-update-tmp/.git "$INSTALL_DIR/" 2>/dev/null || true
    else
        cp -a /tmp/syslog-update-tmp/. "$INSTALL_DIR/"
    fi
    rm -rf /tmp/syslog-update-tmp
else
    echo "项目目录为空，请先运行 deploy.sh 进行部署"
    exit 1
fi

echo ""
echo "[2/4] 更新 Python 依赖..."
if [ -d "venv" ]; then
    source venv/bin/activate
else
    python3 -m venv venv
    source venv/bin/activate
fi
pip install --upgrade pip
pip install flask requests

echo ""
echo "[3/4] 重启服务..."
systemctl restart syslog-server

echo ""
echo "[4/4] 验证服务状态..."
sleep 2
systemctl status syslog-server --no-pager | head -15

echo ""
echo "======================================"
echo "  更新完成！"
echo "======================================"
echo ""
echo "Web 界面: http://\$(hostname -I | awk '{print \$1}'):5000"
echo "日志查看: journalctl -u syslog-server -f"