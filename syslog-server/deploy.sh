#!/bin/bash

# Syslog Server 部署脚本
# 用法: sudo ./deploy.sh

set -e

# 检查是否为 root 用户
if [ "$EUID" -ne 0 ]; then
    echo "请使用 root 用户或 sudo 运行此脚本"
    exit 1
fi

# 配置变量
INSTALL_DIR="/opt/syslog-server"
SERVICE_NAME="syslog-server"
PYTHON_CMD="python3"

echo "=========================================="
echo "  Syslog 日志服务器部署脚本"
echo "=========================================="

# 检查 Python 版本
echo "[1/6] 检查 Python 版本..."
if ! command -v $PYTHON_CMD &> /dev/null; then
    echo "错误: 未找到 Python3，请先安装"
    exit 1
fi

PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | awk '{print $2}')
echo "Python 版本: $PYTHON_VERSION"

# 安装依赖
echo "[2/6] 安装 Python 依赖..."
pip3 install flask netifaces ntplib -q

# 创建安装目录
echo "[3/6] 创建安装目录..."
mkdir -p $INSTALL_DIR

# 复制项目文件
echo "[4/6] 复制项目文件..."
# 如果当前目录就是项目目录，复制所有文件
CURRENT_DIR=$(dirname "$0")
if [ "$CURRENT_DIR" != "$INSTALL_DIR" ]; then
    cp -r "$CURRENT_DIR"/* "$INSTALL_DIR/"
fi

# 创建数据库目录和备份目录
mkdir -p "$INSTALL_DIR/backups"

# 初始化数据库
echo "[5/6] 初始化数据库..."
cd $INSTALL_DIR
$PYTHON_CMD -c "from database.db import Database; Database()" 2>/dev/null || true

# 安装 systemd 服务
echo "[6/6] 安装 systemd 服务..."
cp "$INSTALL_DIR/syslog-server.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable $SERVICE_NAME
systemctl start $SERVICE_NAME

echo ""
echo "=========================================="
echo "  部署完成！"
echo "=========================================="
echo ""
echo "服务状态: systemctl status $SERVICE_NAME"
echo "启动服务: systemctl start $SERVICE_NAME"
echo "停止服务: systemctl stop $SERVICE_NAME"
echo "重启服务: systemctl restart $SERVICE_NAME"
echo "查看日志: journalctl -u $SERVICE_NAME -f"
echo ""
echo "Web 界面: http://<服务器IP>:5000"
echo "默认用户: admin"
echo "默认密码: syslog@2024"
echo ""
echo "Syslog UDP 端口: 5140"
echo "Syslog TCP 端口: 5140"
echo "=========================================="

# 显示服务状态
systemctl status $SERVICE_NAME --no-pager