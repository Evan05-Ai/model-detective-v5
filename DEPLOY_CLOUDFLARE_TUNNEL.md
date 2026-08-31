# Model Detective - Cloudflare Tunnel 部署指南

> 🎯 **目标**：零成本、零绑卡、零服务器，将本地 Flask 应用暴露到公网
>
> **原理**：Cloudflare Tunnel 在你的电脑上运行一个守护进程，主动向 Cloudflare 边缘节点建立出站连接。任何人通过公网 URL → Cloudflare 边缘 → 隧道 → 你的 localhost:5000。无需开放任何入站端口。

---

## 📋 前置条件

| 条件 | 状态 |
|------|------|
| Windows 11 电脑 | ✅ 已确认 |
| Python 虚拟环境 | ✅ `.venv\Scripts\python.exe` 已存在 |
| cloudflared | ✅ 已安装 (v2026.7.3) |
| Cloudflare 账号 | 仅命名隧道模式需要 |

---

## 🚀 快速开始（3 步上线）

### 方法一：双击启动（最简单）

1. 双击运行 `start_tunnel.bat`
2. 等待几秒钟，看到类似输出：
   ```
   Your quick Tunnel has been created! Visit it at:
     https://random-words-1234.trycloudflare.com
   ```
3. **任何人打开这个 URL 就能访问你的 Model Detective！**

### 方法二：PowerShell 启动

```powershell
cd "d:\Ai工作\model-detective"
.\start_tunnel.ps1
```

### 停止服务

- 双击 `stop_tunnel.bat`
- 或直接关闭 `start_tunnel` 窗口
- 或按 `Ctrl+C`

---

## 🔧 两种隧道模式详解

### 模式 A：快速隧道（默认，推荐先用这个）

```
cloudflared tunnel --url http://localhost:5000
```

| 特性 | 说明 |
|------|------|
| URL | `https://随机词.trycloudflare.com` |
| 需要域名 | ❌ 不需要 |
| 需要账号 | ❌ 不需要 |
| URL 稳定性 | ⚠️ 每次重启 cloudflared 会变 |
| 适合场景 | 临时演示、测试、分享 |

### 模式 B：命名隧道（长期使用）

```powershell
.\start_tunnel.ps1 -Named -Hostname "detect.yourdomain.com"
```

| 特性 | 说明 |
|------|------|
| URL | `https://detect.yourdomain.com`（固定不变） |
| 需要域名 | ✅ 需要一个在 Cloudflare 托管的域名 |
| 需要账号 | ✅ 需要 Cloudflare 免费账号 |
| URL 稳定性 | ✅ 永远不变 |
| 适合场景 | 长期使用、正式部署、分享给他人 |

**设置命名隧道步骤**：

1. 注册 Cloudflare 免费账号：https://dash.cloudflare.com/sign-up
2. 添加你的域名到 Cloudflare（修改域名 NS 记录）
3. 运行：
   ```powershell
   .\start_tunnel.ps1 -Named -Hostname "detect.yourdomain.com"
   ```
4. 浏览器会弹出授权页面，选择域名并授权
5. 完成！URL 固定为 `https://detect.yourdomain.com`

---

## 🔄 开机自启（Windows 服务）

### 安装服务（需管理员权限）

1. 先安装 NSSM：
   ```powershell
   winget install nssm.nssm
   ```

2. 以管理员身份打开 PowerShell，运行：
   ```powershell
   cd "d:\Ai工作\model-detective"
   .\install_service.ps1 -Install
   ```

3. 安装后效果：
   - 开机自动启动 Flask + Cloudflare Tunnel
   - 无需手动开窗口
   - 日志写入 `logs/` 目录

### 管理服务

```powershell
# 查看状态（管理员）
.\install_service.ps1 -Status

# 卸载服务（管理员）
.\install_service.ps1 -Uninstall

# 或用 Windows 自带命令
# 注意: 必须写成 sc.exe（带后缀），否则 PowerShell 会把 sc 解析为 Set-Content 别名，
#       误创建名为 start/stop 的垃圾文件
sc.exe start ModelDetectiveFlask
sc.exe stop ModelDetectiveFlask
sc.exe start ModelDetectiveTunnel
sc.exe stop ModelDetectiveTunnel
```

### 查看当前隧道 URL

```powershell
type "d:\Ai工作\model-detective\logs\tunnel_stdout.log"
```

---

## 📊 功能支持情况

| 功能 | 支持情况 | 说明 |
|------|----------|------|
| Quick 检测 | ✅ 完美 | ~15s，无限制 |
| Standard 检测 | ✅ 完美 | ~40s，无限制 |
| Full 检测 | ✅ 完美 | ~70s，无限制 |
| SSE 实时推送 | ✅ 支持 | Cloudflare 代理支持 SSE |
| 后台线程 | ✅ 支持 | 本地完整 Python 环境 |
| tiktoken | ✅ 支持 | 本地已安装 |
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
- 用命名隧道 + 在 Cloudflare 仪表盘调整 `Proxy Read Timeout`
- 或将检测拆分为更小的步骤

### 3. 快速隧道 URL 变化
快速隧道的 URL 在 cloudflared 重启后会变化。如果需要固定 URL：
- 使用命名隧道模式（需要域名）
- 或用 Windows 服务模式（URL 仍会变，但服务会自动重启）

### 4. 带宽消耗
Model Detective 是轻量应用，主要消耗：
- 用户访问页面：~100KB/次
- 检测请求通过隧道出站：~几 KB/次
- 一般家庭宽带完全够用

### 5. 安全性
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

### 问题：端口 5000 被占用
```
解决：运行 stop_tunnel.bat 先停止旧进程
或修改 run_web.py 中的默认端口
```

### 问题：隧道连上了但访问报 502
```
原因：Flask 未启动或崩溃
解决：检查 Flask 是否正常运行
curl http://localhost:5000/health
```

### 问题：SSE 连接断开
```
原因：Cloudflare 代理超时（~100s）
解决：确保检测在 100s 内完成（Quick/Standard 没问题）
Full 检测如果偶尔超时，重试即可
```

---

## 📁 文件清单

| 文件 | 说明 |
|------|------|
| `start_tunnel.bat` | 一键启动（双击运行，最简单） |
| `start_tunnel.ps1` | PowerShell 启动脚本（功能更全） |
| `stop_tunnel.bat` | 一键停止所有进程 |
| `install_service.ps1` | Windows 服务安装/卸载/状态 |
| `logs/` | 服务运行日志目录（自动创建） |

---

## 🎯 总结

| 维度 | 评价 |
|------|------|
| 费用 | **完全免费** |
| 部署时间 | **3 分钟** |
| Full 检测 | **无限制** |
| 维护成本 | 电脑开机即可 |
| 适合场景 | 等 ECS 到位前的完美过渡方案 |
