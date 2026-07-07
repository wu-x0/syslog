#!/bin/bash
set -e

echo "======================================"
echo "  Syslog 日志服务器 更新脚本"
echo "======================================"

INSTALL_DIR="/opt/syslog-server"
cd "$INSTALL_DIR"

echo ""
echo "[0/5] 版本检查..."

get_local_version() {
    if [ -f "config.py" ]; then
        grep "VERSION" config.py | grep -oP "'[^']+'" | head -1 | tr -d "'"
    else
        echo "unknown"
    fi
}

get_remote_version() {
    local remote_config
    remote_config=$(curl -s "https://raw.githubusercontent.com/wu-x0/syslog/main/syslog-server/config.py" 2>/dev/null)
    if [ -n "$remote_config" ]; then
        echo "$remote_config" | grep "VERSION" | grep -oP "'[^']+'" | head -1 | tr -d "'"
    else
        echo "unknown"
    fi
}

LOCAL_VERSION=$(get_local_version)
REMOTE_VERSION=$(get_remote_version)

echo "当前版本: v$LOCAL_VERSION"
echo "最新版本: v$REMOTE_VERSION"

if [ "$LOCAL_VERSION" = "$REMOTE_VERSION" ] && [ "$LOCAL_VERSION" != "unknown" ]; then
    echo ""
    echo "当前版本已是最新版本！"
    read -p "是否仍要执行更新？(y/N): " confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        echo "已取消更新。"
        exit 0
    fi
else
    echo "检测到新版本，开始自动更新..."
fi

echo ""
echo "[1/5] 获取最新代码..."

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
echo "[2/5] 更新 Python 依赖..."
if [ -d "venv" ]; then
    source venv/bin/activate
else
    python3 -m venv venv
    source venv/bin/activate
fi
pip install --upgrade pip
pip install flask requests netifaces

echo ""
echo "[3/5] 重启服务..."
systemctl restart syslog-server

echo ""
echo "[4/5] 验证服务状态..."
sleep 2
systemctl status syslog-server --no-pager | head -15

echo ""
echo "[5/5] 显示新版本号..."
NEW_VERSION=$(get_local_version)
echo "更新后版本: v$NEW_VERSION"

echo ""
echo "======================================"
echo "  更新完成！"
echo "======================================"
echo ""
echo "Web 界面: http://\$(hostname -I | awk '{print \$1}'):5000"
echo "日志查看: journalctl -u syslog-server -f"