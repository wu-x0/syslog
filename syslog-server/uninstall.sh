#!/bin/bash
set -e

echo "======================================"
echo "  Syslog 日志服务器 卸载脚本"
echo "======================================"

INSTALL_DIR="/opt/syslog-server"
SERVICE_NAME="syslog-server"

echo ""
echo "警告：此操作将卸载 Syslog 日志服务器！"
echo ""

read -p "是否保留数据库和备份文件？(Y/n): " keep_data
keep_data=${keep_data:-Y}

if [[ "$keep_data" =~ ^[Yy]$ ]]; then
    echo "将保留数据库文件和备份目录。"
else
    echo "将删除所有数据（包括数据库和备份）。"
fi

read -p "确认要继续卸载吗？(y/N): " confirm
if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "已取消卸载。"
    exit 0
fi

echo ""
echo "[1/5] 停止服务..."
if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
    systemctl stop "$SERVICE_NAME"
    echo "服务已停止。"
else
    echo "服务未运行，跳过停止。"
fi

echo ""
echo "[2/5] 禁用服务..."
if systemctl is-enabled --quiet "$SERVICE_NAME" 2>/dev/null; then
    systemctl disable "$SERVICE_NAME"
    echo "服务已禁用。"
else
    echo "服务未启用，跳过禁用。"
fi

echo ""
echo "[3/5] 移除 systemd 服务文件..."
if [ -f "/etc/systemd/system/$SERVICE_NAME.service" ]; then
    rm -f "/etc/systemd/system/$SERVICE_NAME.service"
    systemctl daemon-reload
    echo "服务文件已移除。"
else
    echo "服务文件不存在，跳过移除。"
fi

echo ""
echo "[4/5] 清理安装目录..."
if [ -d "$INSTALL_DIR" ]; then
    if [[ "$keep_data" =~ ^[Yy]$ ]]; then
        echo "保留数据文件，仅删除程序文件..."
        cd "$INSTALL_DIR"
        find . -maxdepth 1 -type f -name "*.py" -delete
        find . -maxdepth 1 -type f -name "*.sh" -delete
        find . -maxdepth 1 -type f -name "*.txt" -delete
        find . -maxdepth 1 -type f -name "*.service" -delete
        find . -maxdepth 1 -type f -name "*.exe" -delete
        rm -rf venv __pycache__ database syslog_server web templates .git
        rm -f SECURITY.md LICENSE.txt
        echo "程序文件已删除，数据库和备份已保留。"
    else
        rm -rf "$INSTALL_DIR"
        echo "安装目录已完全删除。"
    fi
else
    echo "安装目录不存在，跳过清理。"
fi

echo ""
echo "[5/5] 清理完成..."

echo ""
echo "======================================"
echo "  卸载完成！"
echo "======================================"
echo ""
if [[ "$keep_data" =~ ^[Yy]$ ]] && [ -d "$INSTALL_DIR" ]; then
    echo "数据文件保留在: $INSTALL_DIR"
    echo "  - 数据库: $INSTALL_DIR/syslog.db"
    echo "  - 备份: $INSTALL_DIR/backups/"
    echo ""
    echo "如需彻底删除，请手动执行:"
    echo "  rm -rf $INSTALL_DIR"
fi
echo ""
echo "如需重新安装，请运行 deploy.sh 部署脚本。"
