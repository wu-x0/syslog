@@
*** Begin Patch
*** Update File: README.md
@@
-```bash
-# 下载部署脚本
-curl -sSL -o deploy.sh https://raw.githubusercontent.com/wu-x0/syslog/main/syslog-server/deploy.sh
-
-# 赋予执行权限并运行
-chmod +x deploy.sh
-bash deploy.sh
-```
-
-部署脚本会自动完成：
-- 安装 Python 依赖
-- 创建 Python 虚拟环境
-- 生成 SSL 自签名证书
-- 配置 systemd 服务
-- 启动服务
+```bash
+# 下载部署脚本（仅用于快速演示/测试）
+curl -sSL -o deploy.sh https://raw.githubusercontent.com/wu-x0/syslog/main/syslog-server/deploy.sh
+
+# 赋予执行权限并运行（建议在受控环境中运行）
+chmod +x deploy.sh
+bash deploy.sh
+```
+
+注意：部署脚本为了兼容性示例会以 root 启动服务并绑定低位端口（514/443）。生产环境强烈建议创建专用服务账号并使用反向代理或授予绑定能力，而不是以 root 直接运行主应用。下面是推荐的生产做法。
+
+推荐的生产部署（示例）：
+
+1) 创建系统用户并设置目录权限：
+
+```bash
+sudo useradd --system --no-create-home --shell /usr/sbin/nologin syslog
+sudo mkdir -p /opt/syslog-server
+sudo chown syslog:syslog /opt/syslog-server
+```
+
+2) 使用虚拟环境并安装依赖：
+
+```bash
+cd /opt/syslog-server
+python3 -m venv venv
+source venv/bin/activate
+pip install --upgrade pip
+pip install -r requirements.txt
+```
+
+3) 使用反向代理（nginx）或授予 python 绑定低位端口的能力（示例）：
+
+```bash
+# 推荐：使用 nginx 作为 TLS 终端并将流量反代到 127.0.0.1:8443
+# 或者：授予 python 绑定 443 的能力（风险较高）
+sudo setcap 'cap_net_bind_service=+ep' $(which python3)
+```
+
+4) systemd 服务示例（以非 root 用户运行，若使用反向代理可监听高位端口）:
+
+```ini
+[Unit]
+Description=Syslog Server
+After=network.target
+
+[Service]
+User=syslog
+Group=syslog
+WorkingDirectory=/opt/syslog-server
+Environment="SESSION_SECRET_KEY=<your-secret>"
+Environment="SYSLOG_ADMIN_PASSWORD=<temporary-initial-password>"
+ExecStart=/opt/syslog-server/venv/bin/python3 app.py
+Restart=always
+RestartSec=5
+
+[Install]
+WantedBy=multi-user.target
+```
+
+环境变量说明（强烈建议在 systemd Unit 或容器运行时通过安全方式注入）：
+- SESSION_SECRET_KEY: 用于 Flask session 的随机密钥（应为高熵随机字符串，示例: `python -c "import secrets; print(secrets.token_urlsafe(32))"`）
+- SYSLOG_ADMIN_PASSWORD: 可选的临时管理员密码（仅用于第一次登录并会被自动迁移为哈希后清除）。生产环境建议通过管理界面设置最终密码并删除该 env。 
+
+部署安全提示：
+- 不要将敏感凭据写入仓库。把 secrets 放到 systemd EnvironmentFile、Vault 或容器 secret 管理中。
+- 尽量避免直接以 root 运行应用；创建最小权限的服务账号并限制该账号能力。
+
*** End Patch
