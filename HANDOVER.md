﻿# Model Detective — 交接文档 v6.0

> 创建时间: 2026-08-29 (UTC+8)
> 项目路径: D:\Ai工作\model-detective
> GitHub: git@github.com:Evan05-Ai/model-detective-v5.git (分支: master)
> 当前版本: 后端 v2.9.0 + 前端 Cosmic Galaxy v5.1
> 部署: Cloudflare Tunnel → https://detect.model-detective.online
> 最新 commit: b05b96d refactor: 移除按次收费模式

---

## 一、当前状态总览

### 1.1 已完成的工作（2026-08-29）

| # | 修复内容 | Commit | 状态 |
|---|----------|--------|------|
| 1 | Cloudflare WAF 403 绕过 | `3fa9bed` | ✅ 已提交已推送 |
| 2 | /v1/v1 重复拼接修复 | `d584aaa` | ✅ 已提交已推送 |
| 3 | 成本默认值 $0.5 移除 | `4d68de2` | ✅ 已提交已推送 |
| 4 | OpenAI rstrip('/v1') 陷阱修复 | `74add10` | ✅ 已提交已推送 |
| 5 | 按次收费模式整体移除 | `b05b96d` | ✅ 已提交已推送 |

### 1.2 检测验证结果

gorouter.app 检测**成功**：
- 模型: claude-opus-4-8（实际返回 claude-opus-5）
- 端点: https://gorouter.app/v1，协议: anthropic
- 总分: 76（真伪 69.4 / 能力 98.0 / 合规 86.3）
- 14 次请求，Tokens 111346，费用 $4.3425，耗时 31.4s
- 检测到 Kiro 代理链路

### 1.3 服务状态

| 项目 | 值 |
|------|-----|
| 服务名 | ModelDetectiveFlask (nssm 管理) |
| 启动命令 | python.exe run_web.py |
| 端口 | 5000 |
| 当前 PID | 27072 (启动于 2026-08-29 14:54:13) |
| nssm 配置 | AppExit=Restart (自动重启) |
| 重启方式 | 右键 restart_service.bat → 以管理员身份运行 |
| 公网访问 | https://detect.model-detective.online |

---

## 二、本次修复的技术详情

### 2.1 Cloudflare WAF 403 绕过 (`3fa9bed`)

**问题**: gorouter.app、tabitoken.com 部署了 Cloudflare WAF，拦截 python-requests 默认 User-Agent，返回 403。

**修复**: 在所有 HTTP 请求中注入浏览器 UA 和 Accept 头。

**修改文件**:
- `src/core/http_utils.py` — 新增 `BROWSER_HEADERS` 常量
- `src/protocols/base_client.py` — session 创建时注入
- `src/api_client.py` — session 创建时注入
- `src/core/protocol_resolver.py` — 所有探测请求注入
- `web/app.py` — `/api/probe` 端点注入

### 2.2 /v1/v1 重复拼接修复 (`d584aaa`)

**问题**: `protocol_resolver` 探活成功后无条件追加 `/v1`，导致 `https://gorouter.app/v1/v1`。

**修复**: 追加前检查 base_url 是否已以 `/v1` 结尾。

**修改文件**:
- `src/core/protocol_resolver.py` — 条件追加
- `src/protocols/anthropic/client.py` — 用切片替代 rstrip

### 2.3 rstrip('/v1') 陷阱修复 (`74add10`)

**问题**: `str.rstrip('/v1')` 删除的是字符集合 `{/, v, 1}` 而非字符串后缀。若 URL 包含这些字符会被误删。

**修复**: 用切片 `base[:-3]` 精确移除末尾的 `/v1`。

**修改文件**:
- `src/protocols/openai/client.py` — `_try_resolve_chat_url()` 方法

### 2.4 按次收费模式移除 (`b05b96d`)

**原因**: 用户验证不勾选按次收费也能成功检测。按次收费模式仅减少检测器数量+改变计费方式，非特殊检测逻辑，增加代码复杂度。

**移除范围** (-314 行):
- `web/app.py` — pay_per_call/cost_per_request 参数及检测器过滤逻辑
- `web/static/app.js` — payPerCall/costPerRequest 状态及 initPayPerCall 函数
- `web/templates/index.html` — 按次收费 UI 区块
- `web/static/style.css` — 按次收费相关样式

---

## 三、项目架构

### 3.1 目录结构

```
D:\Ai工作\model-detective\
├── run_web.py                  # 入口脚本
├── restart_service.bat         # 服务重启脚本（需管理员权限）
├── web/
│   ├── app.py                  # Flask 后端（含检测+测评API）
│   ├── templates/
│   │   ├── index.html          # 首页 - API检测
│   │   └── evaluation.html     # 模型测评独立页面
│   └── static/
│       ├── app.js              # 首页前端逻辑
│       ├── style.css           # 全局样式
│       ├── evaluation.js       # 测评页面逻辑
│       └── evaluation.css      # 测评页面样式
├── src/
│   ├── core/
│   │   ├── http_utils.py       # HTTP 工具（含 BROWSER_HEADERS）
│   │   ├── protocol_resolver.py # 协议自动识别
│   │   ├── runner.py           # 检测运行器
│   │   └── modes.py            # 检测模式配置
│   ├── protocols/
│   │   ├── base_client.py      # 协议客户端基类
│   │   ├── openai/
│   │   │   ├── client.py       # OpenAI 客户端（含 URL 自动发现）
│   │   │   └── detectors/      # OpenAI 检测器
│   │   ├── anthropic/
│   │   │   ├── client.py       # Anthropic 客户端
│   │   │   └── detectors/      # Anthropic 检测器
│   │   └── gemini/
│   │       ├── client.py       # Gemini 客户端
│   │       └── detectors/      # Gemini 检测器
│   ├── utils/                  # 共享工具（consistency_scorer, identity_analyzer）
│   └── evaluation/             # 测评引擎
├── MEMORY.md                   # 项目记忆文件
├── HANDOVER.md                 # 本文件
└── .venv/                      # Python 虚拟环境
```

### 3.2 关键代码位置

| 功能 | 文件 | 行号 | 说明 |
|------|------|------|------|
| 探测 URL 生成 | `web/app.py` | 100-118 | `_model_probe_urls()` |
| 探测逻辑 | `web/app.py` | 195-275 | 401/403 处理 |
| 检测执行 | `web/app.py` | 538-616 | `_execute_single_detection()` |
| 协议解析 | `src/core/protocol_resolver.py` | 60-88 | `resolve()` |
| URL 发现 | `src/core/protocol_resolver.py` | 90-150 | `_resolve_openai_base_url()` |
| OpenAI chat URL | `src/protocols/openai/client.py` | 36-85 | `_get_chat_url()` |
| 浏览器头常量 | `src/core/http_utils.py` | - | `BROWSER_HEADERS` |

### 3.3 技术栈

- **后端**: Python 3.12 + Flask
- **前端**: 原生 JS + HTML/CSS（Cosmic Galaxy v5.1 主题）
- **部署**: Cloudflare Tunnel（零成本、零服务器）
- **服务管理**: nssm（Windows 服务）
- **版本控制**: Git + GitHub

---

## 四、历史修复记录（按时间倒序）

### 2026-08-29 按次收费中转站支持修复
- WAF 绕过 + /v1/v1 修复 + rstrip 修复 + 按次收费模式移除
- 详见 MEMORY.md "2026-08-29" 章节

### 2026-08-11 OpenAI 计费检测 Bug 修复 (v2.8.6)
- OpenAI 版计费检测器从 v2.2 升级到 v2.5，与 Anthropic 版一致
- 详见 MEMORY.md "2026-08-11" 章节

### 2026-08-10 Cloudflare Tunnel 部署
- 域名: detect.model-detective.online
- 详见 MEMORY.md "2026-08-10" 章节

### 2026-08-05 Cosmic Galaxy v5.1 宇宙主题
- 深邃宇宙背景 + 银河星云 + 星光闪烁 + 高级玻璃态

### 2026-08-03 v2.7 重构
- Consistency 三维度加权评分
- Identity 语义理解 + 否定检测
- 渐进式探测机制

---

## 五、待办事项 / 已知问题

### 无紧急待办

### 注意事项
1. **服务重启需管理员权限**: 当前 shell 无管理员权限，需右键 `restart_service.bat` → 以管理员身份运行
2. **nssm 自动重启**: 进程退出后 nssm 会自动重启（AppExit=Restart）
3. **按次收费模式已移除**: 不再有 pay_per_call 相关代码和 UI
4. **PythonAnywhere 部署可能过期**: 主要使用 Cloudflare Tunnel 部署

---

## 六、满血启动指南

### 6.1 环境准备

```powershell
# 进入项目目录
cd D:\Ai工作\model-detective

# 激活虚拟环境
.venv\Scripts\Activate.ps1

# 验证 Git 状态
git status
git log --oneline -5
```

### 6.2 启动服务

```powershell
# 方式 1: 通过 nssm 服务（需管理员权限）
restart_service.bat  # 右键 → 以管理员身份运行

# 方式 2: 直接运行（开发模式）
.venv\Scripts\python.exe run_web.py
```

### 6.3 验证服务

```powershell
# 检查端口
netstat -ano | findstr ":5000"

# 检查服务状态
Get-Service ModelDetectiveFlask

# 测试 API
curl http://localhost:5000/api/providers
```

### 6.4 关键文件优先阅读

1. `MEMORY.md` — 项目记忆（完整修复历史）
2. `HANDOVER.md` — 本文件（当前状态）
3. `web/app.py` — 后端核心
4. `src/core/protocol_resolver.py` — 协议解析
5. `src/core/http_utils.py` — HTTP 工具（BROWSER_HEADERS）

---

*此文档由 2026-08-29 会话创建，记录按次收费中转站修复和模式移除的完整状态。*
