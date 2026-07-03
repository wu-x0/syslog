#!/bin/bash

# Syslog Server 更新脚本
# 用法: sudo ./update.sh

set -e

# 检查是否为 root 用户
if [ "$EUID" -ne 0 ]; then
    echo "请使用 root 用户或 sudo 运行此脚本"
    exit 1
fi

# 配置变量
INSTALL_DIR="/opt/syslog-server"
SERVICE_NAME="syslog-server"
BACKUP_DIR="/opt/syslog-server-backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "=========================================="
echo "  Syslog 日志服务器更新脚本"
echo "=========================================="

# 检查服务是否已安装
if [ ! -d "$INSTALL_DIR" ]; then
    echo "错误: 服务未安装，请先运行 deploy.sh"
    exit 1
fi

# 获取新版本目录
NEW_VERSION_DIR=$(dirname "$0")
if [ "$NEW_VERSION_DIR" == "." ]; then
    NEW_VERSION_DIR=$(pwd)
fi

echo "当前安装目录: $INSTALL_DIR"
echo "新版本目录: $NEW_VERSION_DIR"
echo ""

# 备份当前版本
echo "[1/5] 备份当前版本..."
mkdir -p "$BACKUP_DIR"
cp -r "$INSTALL_DIR" "$BACKUP_DIR/syslog-server-$TIMESTAMP"
echo "备份已保存到: $BACKUP_DIR/syslog-server-$TIMESTAMP"

# 备份数据库（非常重要）
echo "[2/5] 备份数据库..."
if [ -f "$INSTALL_DIR/syslog.db" ]; then
    cp "$INSTALL_DIR/syslog.db" "$BACKUP_DIR/syslog-$TIMESTAMP.db"
    echo "数据库已备份到: $BACKUP_DIR/syslog-$TIMESTAMP.db"
fi

# 停止服务
echo "[3/5] 停止服务..."
systemctl stop $SERVICE_NAME || true
echo "服务已停止"

# 更新文件（保留数据库和配置）
echo "[4/5] 更新文件..."

# 保留的文件列表
KEEP_FILES="syslog.db backups"

# 创建临时目录
TEMP_DIR="/tmp/syslog-update-$TIMESTAMP"
mkdir -p "$TEMP_DIR"

# 复制新版本文件
for item in "$NEW_VERSION_DIR"/*; do
    item_name=$(basename "$item")
    # 跳过保留的文件和部署脚本
    if [[ "$KEEP_FILES" != *"$item_name"* ]] && [ "$item_name" != "deploy.sh" ] && [ "$item_name" != "update.sh" ]; then
        cp -r "$item" "$TEMP_DIR/"
    fi
done

# 删除旧文件（保留数据库和备份）
cd "$INSTALL_DIR"
for item in *; do
    if [[ "$KEEP_FILES" != *"$item"* ]]; then
        rm -rf "$item"
    fi
done

# 复制新文件
cp -r "$TEMP_DIR"/* "$INSTALL_DIR/"

# 清理临时目录
rm -rf "$TEMP_DIR"

echo "文件更新完成"

# 启动服务
echo "[5/5] 启动服务..."
cd "$INSTALL_DIR"
systemctl start $SERVICE_NAME

# 等待服务启动
sleep 3

# 检查服务状态
if systemctl is-active --quiet $SERVICE_NAME; then
    echo ""
    echo "=========================================="
    echo "  更新成功！"
    echo "=========================================="
    echo ""
    echo "备份位置: $BACKUP_DIR/syslog-server-$TIMESTAMP"
    echo "数据库备份: $BACKUP_DIR/syslog-$TIMESTAMP.db"
    echo ""
    echo "服务状态: systemctl status $SERVICE_NAME"
    echo "查看日志: journalctl -u $SERVICE_NAME -f"
    echo ""
    systemctl status $SERVICE_NAME --no-pager
else
    echo ""
    echo "警告: 服务启动失败，正在回滚..."
    
    # 回滚
    systemctl stop $SERVICE_NAME || true
    rm -rf "$INSTALL_DIR"/*
    
    # 从备份恢复（排除数据库，因为数据库单独备份了）
    for item in "$BACKUP_DIR/syslog-server-$TIMESTAMP"/*; do
        item_name=$(basename "$item")
        if [ "$item_name" != "syslog.db" ]; then
            cp -r "$item" "$INSTALL_DIR/"
        fi
    done
    
    # 恢复数据库
    if [ -f "$BACKUP_DIR/syslog-$TIMESTAMP.db" ]; then
        cp "$BACKUP_DIR/syslog-$TIMESTAMP.db" "$INSTALL_DIR/syslog.db"
    fi
    
    systemctl start $SERVICE_NAME
    echo "回滚完成，请检查更新文件是否正确"
fi