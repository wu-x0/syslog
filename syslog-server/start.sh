#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d "venv" ]; then
    echo "正在创建虚拟环境..."
    python3 -m venv venv
    source venv/bin/activate
    echo "正在安装依赖..."
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

echo "启动 Syslog 日志服务器..."
python app.py
