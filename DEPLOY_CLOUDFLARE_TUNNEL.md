# Model Detective - Cloudflare Tunnel 部署与运维指南

> 🎯 **目标**：零成本、零绑卡、零服务器，将本地 Flask 应用暴露到公网
>
> **原理**：Cloudflare Tunnel 在你的电脑上运行一个守护进程，主动向 Cloudflare 边缘节点建立出站连接。任何人通过公网 URL → Cloudflare 边缘 → 隧道 → 你的 localhost:5000。无需开放任何入站端口。

---

## 📋 当前生产架构（2026-08-10 落地）

| 组件 | 说明 |
|------|------|
| Flask 服务 | Windows 服务 `ModelDetectiveFlask`（nssm 管理），`.venv\Scripts\python.exe run_web.py`，端口 5000 |
| 隧道 | Cloudflare **命名隧道** `model-detective`，固定 URL https://detect.model-detective.online |
| 隧道配置 | `.cloudflared/config.yml`（ingress: detect.model-detective.online → localhost:5000）+ 凭证 json |
| 公网访问 | https://detect.model-detective.online |

> ⚠️ `.cloudflared/` 目录含隧道凭证，已被 `.gitignore` 排除，**绝不能提交入库**（历史上曾误提交，凭证需在 Cloudflare 后台轮换）。

---

## 🚀 日常运维

### 重启服务（最常用）

右键 `restart_service.bat` → **以管理员身份运行**。脚本会 `net stop/start ModelDetectiveFlask` 并验证 5000 端口。

- nssm 配置了 `AppExit=Restart`：进程意外退出会自动重启，无需人工干预
- **不要**用 taskkill 强杀服务进程——nssm 会立刻把它拉起来

### 查看服务状态

```powershell
# 必须写成 sc.exe（带后缀），否则 PowerShell 会把 sc 解析为 Set-Content 别名，
# 误创建名为 start/stop 的垃圾文件
sc.exe query ModelDetectiveFlask
netstat -ano | findstr ":5000"

# 测试 API
curl http://localhost:5000/api/providers
curl http://localhost:5000/health
```

### 手动启动隧道（平时不需要，隧道由 cloudflared 服务/进程托管）

双击 `start_named_tunnel.bat`（使用 `.cloudflared/` 中的隧道 UUID 与配置）。

---

## 🛠 首次安装（仅新机器需要）

### 1. 安装 Flask 服务

右键 `install_flask_service.bat` → **以管理员身份运行**（内含 winget 安装 nssm 的步骤）。

### 2. 准备 Cloudflare 命名隧道

```powershell
# 登录并生成证书（浏览器授权）
cloudflared tunnel login

# 创建命名隧道（生成凭证 json 到 %USERPROFILE%\.cloudflared\）
cloudflared tunnel create model-detective

# 记下输出的 Tunnel UUID，写入 .cloudflared\config.yml 与 start_named_tunnel.bat
# 在 Cloudflare 仪表盘将域名 CNAME 指向 <UUID>.cfargotunnel.com
```

### 3. 验证

```powershell
cloudflared tunnel run model-detective
# 浏览器访问 https://detect.model-detective.online
```

---

## 📊 功能支持情况

| 功能 | 支持情况 | 说明 |
|------|----------|------|
| Quick 检测 | ✅ 完美 | ~15s，无限制 |
| Standard 检测 | ✅ 完美 | ~40s，无限制 |
| Full 检测 | ✅ 完美 | ~70s，无限制 |
| SSE 实时推送 | ✅ 支持 | Cloudflare 代理支持 SSE |
| HTTPS | ✅ 自动 | Cloudflare 自动管理证书 |
| DDoS 防护 | ✅ 免费 | Cloudflare 边缘防护 |
| 中国访问速度 | ✅ 快 | Cloudflare 有亚洲节点 |

---

## ⚠️ 注意事项

### 1. 电脑休眠问题
电脑休眠/睡眠会导致隧道断开。建议：
- **设置 → 系统 → 电源 → 从不休眠**
- 或用命令行设置：
  ```powershell
  powercfg /change standby-timeout-ac 0
  powercfg /change standby-timeout-dc 0
  ```

### 2. SSE 超时
Cloudflare 代理默认有 ~100 秒超时。Full 检测通常在 70s 内完成，一般没问题。如果偶尔超时：
- 在 Cloudflare 仪表盘调整 `Proxy Read Timeout`
- 或将检测拆分为更小的步骤

### 3. 带宽消耗
Model Detective 是轻量应用，主要消耗：
- 用户访问页面：~100KB/次
- 检测请求通过隧道出站：~几 KB/次
- 一般家庭宽带完全够用

### 4. 安全性
- 隧道是**出站**连接，不需要在路由器/防火墙开放任何入站端口
- 比端口映射/DDNS 安全得多
- Cloudflare 自带 DDoS 防护
- 但注意：URL 是公开的，任何人都能访问（如需加密，可加 Cloudflare Access）

---

## 🆘 故障排查

### 问题：cloudflared 找不到
```
解决：确保安装后重新打开终端，或手动添加到 PATH
set PATH=%PATH%;C:\Program Files (x86)\cloudflared
```

### 问题：隧道连上了但访问报 502
```
原因：Flask 未启动或崩溃
解决：右键 restart_service.bat（管理员）重启 Flask 服务
curl http://localhost:5000/health
```

### 问题：SSE 连接断开
```
原因：Cloudflare 代理超时（~100s）
解决：确保检测在 100s 内完成（Quick/Standard 没问题）
Full 检测如果偶尔超时，重试即可
```

---

## 📁 相关文件清单

| 文件 | 说明 |
|------|------|
| `restart_service.bat` | 重启 Flask 服务（nssm，需管理员） |
| `install_flask_service.bat` | Flask 服务安装（nssm，需管理员） |
| `start_named_tunnel.bat` | 命名隧道手动启动 |
| `C:\Users\evanc\.cloudflared\config-v2.yml` | Cloudflared **服务**专用配置（隧道 model-detective-v2） |
| `.cloudflared/config.yml` | 项目内隧道 ingress 配置（手动运行用，已 gitignore） |
| `.cloudflared/model-detective-v2.json` | 新隧道凭证（已 gitignore） |

---

## 🎯 总结

| 维度 | 评价 |
|------|------|
| 费用 | **完全免费** |
| URL | **固定不变**（命名隧道） |
| Full 检测 | **无限制** |
| 维护成本 | 电脑开机即可 |
