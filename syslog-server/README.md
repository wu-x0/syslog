# Syslog 日志服务器 v1.2.2

基于 Python 的轻量级 Syslog 服务器，支持 UDP/TCP 协议接收、Web 管理界面、日志完整性校验和告警通知。

## 功能特性

- **Syslog 协议支持**: 同时接收 UDP 和 TCP 协议的 Syslog 消息，默认端口 514
- **Web 管理界面**: HTTPS 加密的 Web 界面，支持日志浏览、搜索、统计和系统管理
- **日志完整性保护**: 基于校验和的日志完整性检测，防止日志篡改
- **告警通知**: 支持 Webhook 和邮件告警，可配置高严重性日志、异常速率、完整性失败等告警规则
- **防暴力破解**: IP 级别的登录失败封禁机制，支持配置失败次数和封禁时长
- **系统管理**: 内置 NTP 时间同步、网络接口管理、静态路由配置、时区设置
- **可信主机**: 支持配置可信日志发送主机，过滤非法来源
- **数据备份**: 定时自动备份数据库，支持备份保留策略
- **会话管理**: 超时自动退出，会话过期提醒

## 系统要求

- Python 3.8+
- Linux（推荐 Ubuntu/Debian）
- 可选: systemd（用于服务管理）

## 快速部署

```bash
# 下载部署脚本
curl -sSL -o deploy.sh https://raw.githubusercontent.com/wu-x0/syslog/main/syslog-server/deploy.sh

# 赋予执行权限并运行
chmod +x deploy.sh
bash deploy.sh
```

部署脚本会自动完成：
- 安装 Python 依赖
- 创建 Python 虚拟环境
- 生成 SSL 自签名证书
- 配置 systemd 服务
- 启动服务

## 访问 Web 界面

部署完成后，浏览器访问：

```
https://<服务器IP>:443
```

首次登录使用默认凭据：

| 项目 | 值 |
|------|-----|
| 用户名 | admin |
| 密码 | syslog@2024 |

浏览器会提示证书不安全，点击"高级" -> "继续前往"即可访问。

## 默认端口

| 服务 | 端口 | 协议 |
|------|------|------|
| Web 管理界面 | 443 | HTTPS |
| Syslog UDP | 514 | UDP |
| Syslog TCP | 514 | TCP |

## 更新

```bash
cd /opt/syslog-server && bash update.sh
```

每次更新仅替换代码文件，数据库和证书文件不会被覆盖。

## 卸载

```bash
cd /opt/syslog-server && bash uninstall.sh
```

## 目录结构

```
syslog-server/
├── app.py               # 主入口，SSL 证书生成
├── config.py            # 全局配置
├── database/
│   └── db.py            # SQLite 数据库操作
├── syslog_server/
│   ├── parser.py        # Syslog 消息解析
│   ├── udp_server.py    # UDP 服务端
│   ├── tcp_server.py    # TCP 服务端
│   └── vendor_detector.py # 设备厂商识别
├── web/
│   ├── api.py           # Web API 接口
│   └── templates/
│       ├── index.html   # 管理界面主页
│       └── login.html   # 登录页面
├── alert.py             # 告警模块
├── backup.py            # 数据库备份
├── deploy.sh            # 一键部署脚本
├── update.sh            # 更新脚本
├── uninstall.sh         # 卸载脚本
├── start.sh             # 开发启动脚本
└── requirements.txt     # Python 依赖

```

## 配置说明

主要配置项在 `config.py` 中，运行时修改通过 Web 界面保存到数据库：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| WEB_PORT | 443 | Web 管理界面端口 |
| SYSLOG_UDP_PORT | 514 | Syslog UDP 端口 |
| SYSLOG_TCP_PORT | 514 | Syslog TCP 端口 |
| SESSION_TIMEOUT | 3600 | 会话超时（秒） |
| LOGIN_MAX_ATTEMPTS | 5 | 登录失败封禁阈值 |
| LOGIN_BAN_DURATION | 300 | 封禁时长（秒） |
| MAX_LOG_AGE_DAYS | 180 | 日志保留天数 |
| BACKUP_INTERVAL_HOURS | 24 | 备份间隔（小时） |

## 客户端配置示例

### Rsyslog 转发

```
# /etc/rsyslog.d/forward.conf
*.* @192.168.1.100:514     # UDP
# *.* @@192.168.1.100:514  # TCP
```

### 网络设备

在 Cisco、Huawei 等网络设备的 Syslog 配置中，指向本服务器的 IP 地址和端口 514。
