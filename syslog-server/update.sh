#!/bin/bash
set -e

echo "======================================"
echo "  Syslog 日志服务器 更新脚本"
echo "======================================"

INSTALL_DIR="/opt/syslog-server"
cd "$INSTALL_DIR"

echo ""
echo "[版本检查]"

get_local_version() {
    if [ -f "config.py" ]; then
        grep "VERSION" config.py | sed -n "s/.*'\([^']*\)'.*/\1/p" | head -1
    else
        echo "unknown"
    fi
}

get_remote_version() {
    local remote_raw
    remote_raw=$(curl -s --connect-timeout 5 "https://raw.githubusercontent.com/wu-x0/syslog/main/syslog-server/config.py" 2>/dev/null)
    if [ -n "$remote_raw" ]; then
        echo "$remote_raw" | grep "VERSION" | sed -n "s/.*'\([^']*\)'.*/\1/p" | head -1
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
elif [ "$REMOTE_VERSION" != "unknown" ]; then
    echo "检测到新版本，开始更新..."
else
    echo "无法获取远程版本，继续更新..."
fi

echo ""
echo "[1/6] 停止服务..."
systemctl stop syslog-server 2>/dev/null || true

echo ""
echo "[2/6] 获取最新代码..."

if [ -d .git ]; then
    echo "执行 git pull..."
    git fetch origin main
    git reset --hard origin/main

    # 仓库根目录结构，项目在 syslog-server/ 子目录下
    # 将子目录内容复制到安装目录
    if [ -d "syslog-server" ]; then
        echo "  复制项目文件到安装目录..."
        cp -af syslog-server/. .
        rm -rf syslog-server
    fi

    # 清理仓库根目录多余文件
    rm -f SECURITY.md LICENSE.txt 2>/dev/null || true
elif [ -f "app.py" ]; then
    echo "重新从 GitHub 克隆..."
    git clone --depth 1 https://github.com/wu-x0/syslog.git /tmp/syslog-update-tmp || {
        echo "GitHub 访问失败！请检查网络或手动上传文件"
        exit 1
    }
    if [ -d "/tmp/syslog-update-tmp/syslog-server" ]; then
        cp -af /tmp/syslog-update-tmp/syslog-server/. "$INSTALL_DIR/"
        cp -a /tmp/syslog-update-tmp/.git "$INSTALL_DIR/" 2>/dev/null || true
    else
        cp -af /tmp/syslog-update-tmp/. "$INSTALL_DIR/"
    fi
    rm -rf /tmp/syslog-update-tmp
else
    echo "项目目录为空，请先运行 deploy.sh 进行部署"
    exit 1
fi

echo ""
echo "[3/6] 更新 Python 依赖..."
if [ -d "venv" ]; then
    source venv/bin/activate
else
    python3 -m venv venv
    source venv/bin/activate
fi
pip install --upgrade pip --quiet
pip install flask requests netifaces pyopenssl --quiet

echo ""
echo "[4/6] 清理缓存..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

echo ""
echo "[5/6] 启动服务..."
systemctl start syslog-server

echo ""
echo "[6/6] 验证服务状态..."
sleep 2
systemctl status syslog-server --no-pager | head -15

echo ""
echo "[版本确认]"
NEW_VERSION=$(get_local_version)
echo "更新后版本: v$NEW_VERSION"

echo ""
echo "======================================"
echo "  更新完成！"
echo "======================================"
echo ""
echo "Web 界面: https://\$(hostname -I | awk '{print \$1}'):443"
echo "日志查看: journalctl -u syslog-server -f"
