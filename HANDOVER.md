﻿﻿# Model Detective — 交接文档 v6.3

> 创建时间: 2026-09-01 (UTC+8) · 最后更新: 2026-09-07 (UTC+8)
> 项目路径: D:\Ai工作\model-detective
> GitHub: git@github.com:Evan05-Ai/model-detective-v5.git (分支: master)
> 当前版本: 后端 v3.0.4 + 前端 Cosmic Galaxy v5.1（资产版本 COSMIC_V300_20260906）
> 部署: Cloudflare Tunnel → https://detect.model-detective.online
> 最新基线: pytest 116/116 全绿；v3.0.1~3.0.4 四批已提交（v3.0.4 待重启生效）

---

## 一、当前状态总览

### 1.0d v3.0.4 计费审计分型修正（2026-09-07，0.05x 地面真值校准）

用户实测神秘cc（14 请求全跑通）提供倍率 0.05x 地面真值，暴露计费审计三处误判：固定开销披露把 cache_read 场景成本高估 12.5 倍（文案误写"按 1.25 倍计费"）、缓存透传被误报"虚报缓存计费 -30"、倍率双记账。修正为分型披露（写入 1.25x/读取 0.1x/注入全价 + 全价当量）+ 相干性判定 + 小分母护栏。神秘cc 场景 45→100 分。已知边界（伪造大额 read 不可分辨）为有意取舍，记录于 MEMORY.md。测试 115→116。

### 1.0c v3.0.3 预算信封化（2026-09-07，用户二轮实测驱动）

beiluoxi.top 用 plain input（非 cache_read）上报 ~4.8万 tokens/请求再次冲爆预算——证明 v3.0.1 只修了实例没修本质：**预算依赖被检测方单方面提供的数字，检测深度可被对方任意关停**。v3.0.3 彻底解耦：预算唯一口径改为"请求信封"（我方 payload 估算，`_add_envelope`）；上报数字仅用于费用兜底（钱包上限 quick $5/std $15/full $30，完成优先原则）与"单请求固定开销"计费公平性披露；三维分数支持 None（全 SKIP 维度显示 N/A 而非误导性 0.0）。测试 114→115。详见 MEMORY.md。

### 1.0b v3.0.2 降本增效"纯赚批次"（2026-09-07）

三个零信号损失优化：①探活/预检去重（Resolver.native_probe_succeeded → Runner.skip_preflight，省 1 请求）；②message_id 转被动检测器（省 1 请求且样本量反增，新增重放检测）；③thinking_signature max_tokens 1500→1150。**明确否决 consistency 3→2**（n=2 会把自然噪声从 MINOR 升级为 MAJOR，误报率反升），冻结 knowledge 精简与 token_usage 合并。Standard 检测请求数 ~15→~12。详见 MEMORY.md。

### 1.0a v3.0.1 预算耗尽修复（2026-09-07，用户线上实测发现）

**现象**：Kiro 链路中转站检测时 10/13 检测器 SKIP，"已用 239583/100000"，但实际仅发出 2~3 个请求。
**根因**：中转站每次响应上报数万 `cache_read_input_tokens`（上游系统提示走缓存），旧预算按全价计入 → 2~3 请求冲爆 100k 预算。
**修复**：预算口径下沉客户端层——`TokenUsage.budget_tokens`（Anthropic 剔除 cache_read；OpenAI 剔除 cached_tokens）；Runner 改为"客户端预算计数器 + 预估占用"记账；费用估算按预算口径；新增 3 倍费用保护硬止损。检测器层 58 处 cost_tokens 零改动。
**测试**：test_budget_v3.py 8 项（含截图场景复现），总 111/111。详见 MEMORY.md 同名章节。

### 1.0 v3.0.0 惊艳升级（2026-09-06）

全量代码审查后落地的修复+升级，详见 MEMORY.md 同名章节：

| 类别 | 内容 |
|------|------|
| P1 测评 | 维度选择不再被 difficulty 静默覆盖（`_select_eval_questions` 抽取为可测函数） |
| P1 测评 | option_match 评分重写：明确选项表达 + 反关键词（选错 10%、复述 30%、普通字母噪音 0 分） |
| P1 安全 | 全出站请求 `allow_redirects=False`，堵 SSRF 重定向绕过（request_with_retry 默认 + 3 个客户端流式 + resolver/probe 探测） |
| P2 | Anthropic `_try_resolve_url` 改走 session（浏览器头过 WAF）+ request_with_retry |
| P2 | Standard 题集 36→40 题（boundary 8 题），与 UI 文案一致 |
| P2 | integrity 空响应死逻辑修复（排除 thinking-only 误报） |
| P2 | thinking_signature 中转特征强/弱分级（cf-ray 单一 CDN 头不再误判；标记改前缀匹配） |
| 升级 | model_consistency 接入 system_fingerprint 一致性检查（OpenAI 官方链路真伪信号） |
| 升级 | identity_analyzer 补 GLM/Kimi/豆包等国产模型关键词 + o 系列 claimed 匹配 |
| 升级 | cached_tokens 审计加 prompt≥1024 前置条件（OpenAI 自动缓存门槛，消除误报） |
| 升级 | 置信度系统接入 API 序列化 + 前端展示（v2.6 白写功能启用） |
| 升级 | PROVIDERS 前端统一从 /api/providers 拉取（消除三处硬编码） |
| 升级 | 测评并发闸门 `_EVAL_SEMA=2` |
| 升级 | prefers-reduced-motion 无障碍适配（两份 CSS + starfield.js + evaluation.js） |
| 清理 | index.html 隐藏测评区（~200 行死 HTML）、app.js 评测死代码（~800 行）、consistency_v27.py 死文件、重复候选 URL、cost_usd 死属性 |
| 测试 | 新增 tests/test_core/test_scoring_v3.py（25 项），总数 78→103 全绿 |

**注意**：改动需重启 Flask 服务才在线上生效（右键 restart_service.bat 管理员运行）。DNS rebinding（TOCTOU 二次解析）为已知残留限制，文档化未修——修需 pinned-IP 连接，性价比低。

### 1.1 已完成的工作（2026-09-01 自检审查）

| # | 修复内容 | Commit | 状态 |
|---|----------|--------|------|
| 1 | DEBUG print 泄露 API Key | `ee3b39b` | ✅ 已推送 |
| 2 | OpenAI cache 字段名错误 | `ee3b39b` | ✅ 已推送 |
| 3 | SSRF DNS 解析防护加强 | `ee3b39b` | ✅ 已推送 |
| 4 | Anthropic config 注释不一致 | `ee3b39b` | ✅ 已推送 |
| 5 | _EVAL_JOBS 清理机制 | `ee3b39b` | ✅ 已推送 |
| 6 | GitHub 链接修复 | `ee3b39b` | ✅ 已推送 |
| 7 | URL 自动发现验证加强 | `ee3b39b` | ✅ 已推送 |

### 1.2 前次修复（2026-08-29）

| # | 修复内容 | Commit | 状态 |
|---|----------|--------|------|
| 1 | Cloudflare WAF 403 绕过 | `3fa9bed` | ✅ 已提交已推送 |
| 2 | /v1/v1 重复拼接修复 | `d584aaa` | ✅ 已提交已推送 |
| 3 | 成本默认值 $0.5 移除 | `4d68de2` | ✅ 已提交已推送 |
| 4 | OpenAI rstrip('/v1') 陷阱修复 | `74add10` | ✅ 已提交已推送 |
| 5 | 按次收费模式整体移除 | `b05b96d` | ✅ 已提交已推送 |

### 1.3 检测验证结果

gorouter.app 检测**成功**：
- 模型: claude-opus-4-8（实际返回 claude-opus-5）
- 端点: https://gorouter.app/v1，协议: anthropic
- 总分: 76（真伪 69.4 / 能力 98.0 / 合规 86.3）
- 14 次请求，Tokens 111346，费用 $4.3425，耗时 31.4s
- 检测到 Kiro 代理链路

### 1.4 服务状态

| 项目 | 值 |
|------|-----|
| Flask 服务 | ModelDetectiveFlask (nssm 管理)，python.exe run_web.py，端口 5000 |
| 隧道服务 | Cloudflared（Windows 服务，开机自启），承载隧道 model-detective-v2 |
| 隧道配置 | 服务用 `C:\Users\evanc\.cloudflared\config-v2.yml`；手动运行用项目 `.cloudflared/config.yml` |
| nssm 配置 | AppExit=Restart (自动重启) |
| 重启方式 | 右键 restart_service.bat → 以管理员身份运行 |
| 公网访问 | https://detect.model-detective.online |

### 1.5 2026-09-03 工作区大清理

- 移除误入仓库的根目录第三方包 461 个跟踪文件（阿里云 FC `pip install -t .` 残留），依赖改由 .venv 提供（已补装 tiktoken/gunicorn/regex，flask/requests 等版本不变）
- 清理约 55 个历史残留文件（检测输出、一次性脚本、过时设计稿、AI 工具目录、缓存）
- 阿里云 FC 部署文件移除；启动脚本 8 个整合为 3 个
- `.cloudflared/` 凭证解除 git 跟踪；scripts/ 中含硬编码 Key 的一次性测试脚本已删除
- 详见 MEMORY.md "2026-09-03 工作区大清理" 章节

### 1.6 2026-09-03 Cloudflare 隧道凭证轮换（同日续）

- 背景：旧隧道凭证 `.cloudflared/model-detective.json` 曾随 commit `9cbb8dc` 推送到公开 GitHub 仓库（仓库为公开仓库），且 origin/master 顶端仍保留
- 新建隧道 **model-detective-v2**（UUID `3afd1108-3572-4fbe-b841-b5f7cd9d23fa`）；CNAME 经 `tunnel route dns --overwrite-dns` 切换
- Cloudflared 服务启动参数改为 `tunnel --config C:\Users\evanc\.cloudflared\config-v2.yml run 3afd1108-…`（原 token-file 模式废弃）；`C:\ProgramData\cloudflared\token`（含旧 Secret）已删除
- **旧隧道 model-detective（fd06a112-…）已删除 → 泄露的旧 TunnelSecret 永久失效**
- 泄露的 4 个中转站 API Key（beikun×1 / findcg×2 / qlhazycoder×1）用户已全部作废
- 技术坑记录见 MEMORY.md 同名章节

---

## 二、本次修复的技术详情（2026-09-01 自检审查）

### 2.1 DEBUG print 泄露 API Key
**问题**: `src/protocols/anthropic/client.py` 中 6 处 `print(f"[DEBUG]...")` 语句，其中第 142 行打印 `headers={dict(resp.headers)}`，包含 `x-api-key` 认证头。
**修复**: 删除全部 6 处 DEBUG print 语句。

### 2.2 OpenAI cache 字段名错误
**问题**: `src/protocols/openai/detectors/billing_integrity.py` 使用 `cache_read_tokens`/`cache_creation_tokens`（Anthropic 字段名），OpenAI 的缓存信息在 `usage.prompt_tokens_details.cached_tokens` 中。
**修复**: 改为从 `resp.raw_response` 中提取 OpenAI 格式的 `prompt_tokens_details.cached_tokens`。

### 2.3 SSRF 防护加强
**问题**: `_validate_base_url_no_ssrf` 只做字符串前缀匹配，域名解析到内网 IP 可绕过。
**修复**: 添加 DNS 解析 + `ipaddress` 内网 CIDR 检查（127.0.0.0/8, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.0.0/16, 0.0.0.0/8, ::1/128, fc00::/7, fe80::/10）。

### 2.4 Anthropic config 注释更新
**问题**: 注释中的权重表与 v2.6 代码不一致（identity 0.10→0.12, behavioral_signature 0.08→0.04, knowledge 0.07→0.06, integrity 0.06→0.08, long_context 0.02→0.03）。
**修复**: 更新注释匹配代码中的实际权重值。

### 2.5 _EVAL_JOBS 清理机制
**问题**: `_EVAL_JOBS` 字典无清理机制，长时间运行内存持续增长。
**修复**: 添加 `_gc_eval_jobs()` 函数（上限 200，清理已完成/错误任务），在创建新任务时调用。

### 2.6 GitHub 链接修复
**问题**: `index.html` 中 GitHub 链接指向 `https://github.com`（通用首页）。
**修复**: 改为 `https://github.com/Evan05-Ai/model-detective-v5`。

### 2.7 URL 自动发现验证加强
**问题**: `_try_resolve_url` 只要 200 + JSON dict 就缓存 URL，中转站错误页面可能返回 200 + JSON。
**修复**: 增加 Anthropic 响应字段验证（要求包含 `content`/`error` + `role`/`id`）。

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
│   │   ├── modes.py            # 检测模式配置
│   │   ├── scorer.py           # 三维加权评分引擎
│   │   ├── models.py           # 数据模型定义
│   │   ├── detector_base.py    # 检测器基类
│   │   └── error_standards.py  # 错误评分标准
│   ├── protocols/
│   │   ├── base_client.py      # 协议客户端基类
│   │   ├── openai/
│   │   │   ├── client.py       # OpenAI 客户端（含 URL 自动发现）
│   │   │   ├── config.py       # OpenAI 检测器配置
│   │   │   └── detectors/      # OpenAI 检测器
│   │   ├── anthropic/
│   │   │   ├── client.py       # Anthropic 客户端
│   │   │   ├── config.py       # Anthropic 检测器配置
│   │   │   └── detectors/      # Anthropic 检测器
│   │   └── gemini/
│   │       ├── client.py       # Gemini 客户端
│   │       └── detectors/      # Gemini 检测器
│   ├── utils/                  # 共享工具（consistency_scorer, identity_analyzer）
│   └── evaluation/             # 测评引擎
├── MEMORY.md                   # 项目记忆文件
<|endoftext|>
```

### 3.2 关键代码位置

| 功能 | 文件 | 行号 | 说明 |
|------|------|------|------|
| SSRF 防护 | `web/app.py` | 121-195 | `_validate_base_url_no_ssrf()`（含 DNS 解析） |
| 探测 URL 生成 | `web/app.py` | 100-118 | `_model_probe_urls()` |
| 检测执行 | `web/app.py` | 538-616 | `_execute_single_detection()` |
| 协议解析 | `src/core/protocol_resolver.py` | 60-88 | `resolve()` |
| URL 发现 | `src/core/protocol_resolver.py` | 90-150 | `_resolve_openai_base_url()` |
| OpenAI chat URL | `src/protocols/openai/client.py` | 36-85 | `_get_chat_url()` |
| 浏览器头常量 | `src/core/http_utils.py` | - | `BROWSER_HEADERS` |
| 评分引擎 | `src/core/scorer.py` | - | `calculate_scores()` + `determine_verdict()` |
| 后端来源推断 | `src/core/scorer.py` | - | `infer_backend_source()` + `calibrate_by_backend()` |

### 3.3 技术栈

- **后端**: Python 3.12 + Flask
- **前端**: 原生 JS + HTML/CSS（Cosmic Galaxy v5.1 主题）
- **部署**: Cloudflare Tunnel（零成本、零服务器）
- **服务管理**: nssm（Windows 服务）
- **版本控制**: Git + GitHub

---

## 四、历史修复记录（按时间倒序）

### 2026-09-03（续）Cloudflare 隧道凭证轮换
- 新隧道 model-detective-v2（3afd1108-3572-4fbe-b841-b5f7cd9d23fa）上线，CNAME 已切换，旧隧道已删除、旧 Secret 永久失效
- Cloudflared 服务改为本地配置文件模式（config-v2.yml），ProgramData 旧 token 文件已删
- 泄露 Key 已由用户作废；零停机完成（切换期间由临时 connector 承载流量）

### 2026-09-03 工作区大清理
- **根目录第三方包移除**（461 个 git 跟踪文件）：2026-08-10 已放弃的阿里云 FC 部署执行 `pip install -r requirements.txt -t .` 产生，且当时用 Python 3.14 安装——cp314 二进制在 3.12 venv 下无法加载，还遮蔽 venv 同名包。依赖改由 .venv 提供
- **约 55 个零引用残留文件删除**：检测/测评输出 txt×33 + json×10、一次性自检脚本（_test_identity/_v1_verify/_v2_selfcheck）、空壳脚本（update_consistency.py 0B / update_handover.py 36B）、无关的股票 demo index.html、过时设计稿（FUSION_PLAN/STARTUP_GUIDE/test_framework/test_questions(+v2)/core_summary/execution_guide/scoring_sheet/visualization_template/STARTUP_PROMPT，真实题库在 eval_engine.py 内置常量）
- **scripts/ 清理**：删除 8 个 2026-07 一次性中转站测试脚本（含硬编码 API Key）；保留 generate_test_pdf.py、billing_audit.py
- **阿里云 FC 五件套删除**：s.yaml、aliyun_fc_app.py、deploy_fc.sh/ps1、bootstrap
- **启动脚本整合 8→3**：保留 restart_service.bat、install_flask_service.bat、start_named_tunnel.bat；删除 stop_tunnel.bat（与 nssm 自动重启冲突）、start_web.bat（系统 Python 损坏）、start_tunnel.bat/ps1（快速隧道旧方案）、install_service.ps1（与 bat 重叠）
- **安全加固**：.cloudflared/ 凭证解除 git 跟踪并 ignore（文件保留在磁盘）；README 项目树校正；DEPLOY_CLOUDFLARE_TUNNEL.md 重写为 nssm + 命名隧道现状
- **AI 工具目录**：.codebuddy/.workbuddy/.codeartsdoer 删除；.codegraph 保留（daemon 活跃）

### 2026-09-01 项目自检审查修复
- 7 项安全与逻辑问题修复（DEBUG print 泄露、cache 字段名、SSRF、注释、内存清理、GitHub 链接、URL 验证）
- 详见 MEMORY.md "2026-09-01" 章节

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
4. **PythonAnywhere 部署可能过期**: 主要使用 Cloudflare Tunnel 部署。备用实例 https://Evan05Ai.pythonanywhere.com（Beginner 免费版：CPU 100 秒/天，Quick 检测可用、Standard 约 1-2 次/天、Full 不可用；需每月在控制台点击 "Run until 1 month from today" 续命）
5. **全部提交已推送（2026-09-03）**: 远端顶端 `ef371e1`，本地与 origin/master 同步；公开仓库顶端 125 个文件零敏感内容（历史 blob 中的旧秘密均已失效，Secret Scanning 报警可忽略）
6. **隧道凭证已轮换完成（2026-09-03）**: 旧隧道已删除、git 历史中的旧凭证已失效，无需再做 history rewrite；新服务配置在 `C:\Users\evanc\.cloudflared\config-v2.yml`（纯 ASCII 路径，勿改为含中文的路径——提权脚本/服务参数中的中文会被 GBK 乱码）
7. **泄露的 API Key 已作废（2026-09-03）**: beikun.xyz×1、findcg×2、qlhazycoder×1 共 4 个 Key 用户已删除；如这些站仍在用，生成新 Key 后勿写入任何 git 跟踪文件（放 `config.local.json` 或环境变量）
8. **本机测公网会被代理干扰**: 本机 curl 访问 detect.model-detective.online 偶发 10 秒黑洞（v2rayN/mitmproxy 层），`--noproxy "*"` 也可能命中；验证服务是否正常请用外部视角（手机流量/在线工具）

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

## 七、新会话（智能体）满血启动提示词

> 新开任意 AI 对话框时，把下面整段复制为第一条消息，即可满血继承上下文。

```
你在 Model Detective 项目（D:\Ai工作\model-detective）工作，这是一个 AI API 中转站真伪检测 + 模型能力测评的 Python Flask 应用。

第一步（必做）：完整阅读项目根目录的 HANDOVER.md（当前状态与交接，本提示词所在文件）和 MEMORY.md（完整修复历史）。这两份是被 git 跟踪的智能体身份文件，一切状态以它们为准，不要当作残留清理。今日工作日志见 docs/WORK_LOG_2026-09-03.md。

关键约束（违反会出事故）：
1. Python 一律用 .venv\Scripts\python.exe；严禁在项目根目录执行 pip install -t .（曾把 461 个第三方包误提交进仓库）
2. .cloudflared/ 内是隧道凭证，已 gitignore，绝不能入库或外发；隧道为 model-detective-v2，由 Windows 服务 Cloudflared 托管（服务配置 C:\Users\evanc\.cloudflared\config-v2.yml，纯 ASCII 路径，勿改成含中文的路径）
3. 重启服务需管理员权限：右键 restart_service.bat 以管理员身份运行；不要 taskkill 服务进程（nssm 配置了自动重启）
4. 本机 curl 访问公网（含 github.com）会被 v2rayN/mitmproxy 代理层间歇吞包（约 10 秒黑洞），验证站点/仓库是否正常必须用外部视角（WebFetch、手机流量）
5. 任何 API Key 不准写进 git 跟踪的文件（放 config.local.json 或环境变量）
6. 改动代码后运行 .venv\Scripts\python.exe -m pytest tests/（当前 111 用例全部通过）
7. 修改 start 脚本时注意：cloudflared 的 --config 必须放在 tunnel 之后、run 之前
8. 所有出站 HTTP 请求默认 allow_redirects=False（v3.0 SSRF 防护，新代码勿改回）
9. 检测预算口径：缓存读取（cache_read/cached_tokens）不占用 Runner 预算（v3.0.1），新增检测器勿再用 usage.total_tokens 做预算判断

当前基线：后端 v3.0.1 + 前端 Cosmic Galaxy v5.1（资产 COSMIC_V300_20260906）；部署 https://detect.model-detective.online；pytest 111/111；无遗留安全待办（DNS rebinding TOCTOU 为已知残留限制）。
```

---

*此文档由 2026-09-03 会话更新：工作区大清理 + 隧道凭证轮换 + 全量推送 + 自检修正。*
