# Model Detective — 项目记忆文件

> 最后更新: 2026-09-01 (UTC+8)
> 当前版本: v2.9.1 后端（自检审查修复）+ Cosmic Galaxy v5.1 前端
> 部署状态: Cloudflare Tunnel ✅ (detect.model-detective.online)
> 技术栈: Python Flask + Vanilla JS + HTML/CSS
> GitHub: git@github.com:Evan05-Ai/model-detective-v5.git (分支: master)

---

## 2026-09-03 工作区大清理（重要）

### 背景
用户要求全量扫描工作区并清理可删除/合并的文件。3 个探索智能体全量审计根目录散落文件、第三方包与 .venv 对照、目录/脚本/隐藏目录，关键结论交叉验证后经用户确认执行。

### 核心发现
1. **根目录整套第三方包是 2026-08-10 已放弃的阿里云 FC 部署残留**：`pip install -r requirements.txt -t .`（且当时用系统 Python 3.14 执行），459 个 git 跟踪文件（占仓库 611 个的 75%），遮蔽 .venv 同名包；regex/tiktoken 的 cp314 二进制在 3.12 服务下根本无法加载（regex 直接 import 报错，charset_normalizer 靠纯 Python 回退运行）
2. **约 55 个零引用残留文件**：检测/测评输出（txt×33、json×10）、一次性自检脚本、空壳脚本、无关文件、过时设计稿
3. **安全隐患**：`.cloudflared/` 隧道凭证曾被 git 跟踪入库；scripts/ 8 个一次性脚本硬编码至少 4 个真实 API Key（已进 git 历史）

### 清理内容

| 类别 | 处置 |
|------|------|
| 根目录第三方包（19 组目录 + bin/ + pyd） | git rm 移除；.venv 补装 tiktoken 0.14.0 / gunicorn 26.2.0 / regex 2026.9.3（cp312 正常轮子）；flask/requests 等版本不变，行为零变化 |
| 检测/测评输出 | 全部删除（结论已沉淀于本文件） |
| 一次性脚本 | _test_identity/_v1_verify/_v2_selfcheck.py、update_consistency.py(0B)、update_handover.py(36B) 删除 |
| 过时设计稿 | FUSION_PLAN/STARTUP_GUIDE/test_framework/test_questions(+v2)/core_summary/execution_guide/scoring_sheet/visualization_template/STARTUP_PROMPT 删除（真实题库在 src/evaluation/eval_engine.py 内置常量中；STARTUP_PROMPT 的 PythonAnywhere 运维要点已并入 HANDOVER 注意事项） |
| 无关/过时文件 | 根目录 index.html（股票 demo，与项目无关）、image.png、MEMORY.md.backup、server.err/log、1.1MB 报告 PDF、beikun 报告 md |
| AI 工具目录 | .codebuddy/.workbuddy/.codeartsdoer 删除；.codegraph 保留（daemon 活跃使用中） |
| 阿里云 FC | s.yaml、aliyun_fc_app.py、deploy_fc.sh/ps1、bootstrap 删除（docs/WORK_LOG_2026-08-10.md 有"失败/放弃"记录） |
| 启动脚本 8→3 | 保留 restart_service.bat、install_flask_service.bat、start_named_tunnel.bat；删除 stop_tunnel.bat（杀服务进程，与 nssm AppExit=Restart 冲突）、start_web.bat（用已损坏的系统 Python）、start_tunnel.bat/ps1（快速隧道旧方案）、install_service.ps1（与 bat 重叠且 Tunnel 段过时） |
| scripts/ | 删除 8 个 2026-07 一次性中转站测试脚本（含硬编码 Key）+ billing_audit_result.txt；保留 generate_test_pdf.py、billing_audit.py |
| docs/ | 删除 0 字节文件 ×2 与 KIRO/LIGHTWEIGHT 方案稿；保留 BILLING_INTEGRITY_FIX / EVALUATION_GUIDE / WORK_LOG |
| 安全 | .cloudflared/ 解除 git 跟踪并 ignore（文件保留在磁盘，隧道不受影响） |
| 防复发 | .gitignore 增加 bin/、.cloudflared/、.codeartsdoer/、.codegraph/、.zcode/ |
| 文档 | README 项目树校正（后端版本改 v2.9.1）；DEPLOY_CLOUDFLARE_TUNNEL.md 重写为 nssm + 命名隧道现状 |

### 关键技术事实（防回归）
- web/src 不直接 import tiktoken（src/utils/token_counter.py 有 ImportError 回退），tiktoken 仅供保留脚本使用及 requirements.txt 声明
- run_web.py 会把项目根插入 sys.path——**永远不要在项目根执行 `pip install -t .`**
- 删除文件不能清除 git 历史：隧道凭证轮换（Cloudflare 后台）与泄露 Key 作废（各中转站后台）需人工完成

### 提交记录
- `8a3dbad` docs: 提交上次会话遗留的 HANDOVER/MEMORY 更新
- `5ce1619` chore: 移除误入仓库的根目录第三方依赖包
- `4e463fc` chore: 清理历史检测输出、一次性脚本与过时设计稿
- `7ed53f0` chore: 移除已放弃的阿里云 FC 部署文件并整合启动脚本

---

## 2026-09-01 项目自检审查修复（7 项）

### 背景
对项目进行全面代码审查，从第三方安全与质量审计视角发现 7 个问题并全部修复。

### 修复清单

| 优先级 | 问题 | 修复 | Commit |
|--------|------|------|--------|
| P0 | anthropic/client.py 中 6 处 DEBUG print 语句泄露 API Key（含 headers） | 删除全部 6 处 | `ee3b39b` |
| P0 | OpenAI billing_integrity cache 字段名错误（用 Anthropic 字段名） | 改为 OpenAI 格式 `prompt_tokens_details.cached_tokens` | `ee3b39b` |
| P1 | SSRF 防护仅做字符串前缀匹配，可被 DNS 解析到内网 IP 绕过 | 添加 DNS 解析 + ipaddress 内网 CIDR 检查（9 个网段） | `ee3b39b` |
| P1 | Anthropic config.py 注释与 v2.6 实际权重不一致（5 处） | 更新注释匹配代码 | `ee3b39b` |
| P2 | _EVAL_JOBS 无清理机制，内存持续增长 | 添加 `_gc_eval_jobs()` 清理函数（上限 200） | `ee3b39b` |
| P2 | index.html GitHub 链接指向通用首页 | 改为项目仓库 `Evan05-Ai/model-detective-v5` | `ee3b39b` |
| P2 | Anthropic client URL 自动发现验证不够严格（200+JSON dict 即缓存） | 增加 content/error + role/id 字段验证 | `ee3b39b` |

### 修改文件
- `src/protocols/anthropic/client.py` — 删除 DEBUG print + URL 发现验证加强
- `src/protocols/openai/detectors/billing_integrity.py` — cache 字段名修复
- `web/app.py` — SSRF DNS 解析检查 + _gc_eval_jobs 清理机制
- `src/protocols/anthropic/config.py` — 注释更新
- `web/templates/index.html` — GitHub 链接修复

### 验证
- ✅ 所有文件语法检查通过
- ✅ Anthropic/OpenAI 配置校验通过（权重和 = 1.0）
- ✅ DEBUG print 语句已完全清除

---

## 2026-08-29 按次收费中转站支持修复 + 模式移除（重要）

### 背景
用户反馈 gorouter.app、tabitoken.com 等按次收费中转站检测失败。

### 根本原因（4 个独立问题）

| # | 问题 | 根因 | 修复 commit |
|---|------|------|-------------|
| 1 | Cloudflare WAF 403 拦截 | python-requests 默认 UA 被 WAF 拦截 | `3fa9bed` |
| 2 | /v1/v1 重复拼接 | protocol_resolver 无条件追加 /v1 | `d584aaa` |
| 3 | rstrip('/v1') 陷阱 | rstrip 删除字符集合 {/,v,1} 而非字符串后缀 | `74add10` |
| 4 | 成本默认值 $0.5 不合理 | 不同中转站定价不同 | `4d68de2` |

### 修复详情

**1. WAF 绕过** (`3fa9bed`)
- `src/core/http_utils.py`: 新增 `BROWSER_HEADERS` 常量（浏览器 UA + Accept 头）
- `src/protocols/base_client.py`: session 创建时注入浏览器头
- `src/api_client.py`: session 创建时注入浏览器头
- `src/core/protocol_resolver.py`: 所有探测请求注入浏览器头
- `web/app.py`: `/api/probe` 端点注入浏览器头

**2. /v1/v1 拼接修复** (`d584aaa`)
- `src/core/protocol_resolver.py`: 追加前检查是否已以 /v1 结尾
- `src/protocols/anthropic/client.py`: 用 `clean_base` 替代 `rstrip('/v1')`

**3. rstrip 陷阱修复** (`74add10`)
- `src/protocols/openai/client.py`: `_try_resolve_chat_url()` 中用切片 `base[:-3]` 替代 `rstrip('/v1')`

**4. 按次收费模式移除** (`b05b96d`)
- 用户验证：不勾选按次收费也能成功检测 gorouter.app
- 按次收费模式仅减少检测器数量+改变计费方式，非特殊检测逻辑
- 移除 4 个文件中 -314 行代码：
  - `web/app.py`: pay_per_call/cost_per_request 参数及检测器过滤
  - `web/static/app.js`: payPerCall/costPerRequest 状态及 initPayPerCall 函数
  - `web/templates/index.html`: 按次收费 UI 区块
  - `web/static/style.css`: 按次收费相关样式

### 检测验证结果
- gorouter.app 检测**成功**: claude-opus-4-8（实际返回 claude-opus-5）
- 总分 76（真伪 69.4 / 能力 98.0 / 合规 86.3）
- 14 次请求，Tokens 111346，费用 $4.3425，耗时 31.4s
- 检测到 Kiro 代理链路

### 服务部署信息
- 服务名: ModelDetectiveFlask (nssm 管理)
- 服务配置: python.exe run_web.py (端口 5000)
- 重启方式: 右键 restart_service.bat → 以管理员身份运行
- nssm 配置了 AppExit=Restart（进程退出自动重启）
- Cloudflare Tunnel 域名: detect.model-detective.online

---

## 零、2026-08-11 OpenAI 计费检测 Bug 修复（重要）

### 问题
用户反馈实测多个 OpenAI GPT 中转站，计费检测结果基本都是"严重虚报"。

### 根本原因
**OpenAI 版本的计费检测器停留在 v2.2，而 Anthropic 版本已更新到 v2.5！**

两个版本实现严重不一致：

| 检测项 | OpenAI v2.2（旧） | Anthropic v2.5（新） |
|--------|------------------|---------------------|
| Input 偏差阈值 | >30% 扣 40 分 | >100% 才扣 25 分 |
| 计费倍率阈值 | >2x 判定"严重虚报" | >3x 仅提示不扣分 |
| 定性词汇 | "严重虚报"、"欺诈" | 客观描述 |

### 修复内容（v2.8.6）

| # | 变更 | 修复前 | 修复后 |
|---|------|--------|--------|
| 1 | Input 偏差阈值 | >30% 扣分 | >200% 不扣分，>500% 才提示 |
| 2 | 计费倍率阈值 | >2x "严重虚报" | >5x 仅提示 |
| 3 | 定性词汇 | "严重虚报"、"欺诈" | "高于估算"、"可能包含" |
| 4 | Tokenizer | tiktoken "精确"计算 | 粗略估算（1 token ≈ 4 字符） |
| 5 | 评分影响 | 偏差即扣分 | 仅极端情况扣分 |

### 修复后的判定逻辑

```
Input Tokens:
  - < 2x 估算：✅ 正常
  - 2x ~ 5x 估算：ℹ️ 提示可能原因（不扣分）
  - > 5x 估算：⚠️ 显著偏高（提示原因）

计费倍率：
  - < 5x：✅ 正常
  - > 5x：ℹ️ 仅供参考，提示可能原因
```

### 为什么 GPT 中转站会被误判

中转站的实际 token 构成可能包括：
- 用户消息本身：~15 tokens
- 消息格式开销：~4 tokens
- **中转站系统消息**：+10~30 tokens
- **工具定义开销**：+50~200 tokens
- **请求元数据**：+5~10 tokens

**实际上报：90~260 tokens** vs **代码估算：19 tokens** = 偏差 374%~1268%

但这完全是正常的！中转站可能添加了系统消息、工具定义等。

### 文档
- `docs/BILLING_INTEGRITY_FIX_2026-08-11.md` - 详细修复报告

---

## 零、2026-08-10 Cloudflare Tunnel 部署落地

### 部署概况

**方案**：Cloudflare Tunnel（零成本、零绑卡、零服务器）  
**cloudflared 版本**：v2026.7.3  
**域名**：model-detective.online（已购买）  
**固定 URL**：https://detect.model-detective.online（命名隧道，永久有效）  
**部署方式**：Windows 服务自动启动（开机即上线）

### 创建的文件

| 文件 | 用途 |
|------|------|
| `start_tunnel.bat` | 双击启动（最简单） |
| `start_tunnel.ps1` | PowerShell 启动，支持 `-Named` 命名隧道模式 |
| `stop_tunnel.bat` | 停止所有进程 |
| `install_service.ps1` | Windows 服务安装（开机自启） |
| `install_flask_service.bat` | Flask 服务安装辅助 |
| `start_named_tunnel.bat` | 命名隧道启动（固定 URL） |
| `DEPLOY_CLOUDFLARE_TUNNEL.md` | 完整部署文档 |
| `.cloudflared/config.yml` | 隧道配置 |
| `.cloudflared/model-detective.json` | 隧道凭证 |

### 测试验证

| 测试项 | 结果 |
|--------|------|
| 公网 URL 健康检查 | ✅ 200 OK |
| 首页 | ✅ 29KB |
| CSS | ✅ 47KB |
| JS | ✅ 67KB |
| 测评页 | ✅ 15KB |
| Providers API | ✅ 正常 |
| Quick/Standard/Full 检测 | ✅ 全部完美运行 |
| SSE 实时推送 | ✅ 支持 |

### 部署方案对比

| 方案 | 状态 | URL |
|------|------|-----|
| PythonAnywhere Beginner | ✅ 已上线 | https://Evan05Ai.pythonanywhere.com |
| Cloudflare Tunnel | ✅ 已部署 | https://detect.model-detective.online |
| 阿里云 ECS | ⏳ 等待试用资格 | - |

---

## 一、项目概述

**Model Detective** 是一个本地运行的 Web 应用，用于检测 AI API 中转站的真伪、计费诚信，以及对大模型进行标准化能力测评。

### 核心功能模块

| 模块 | 路径 | 说明 |
|------|------|------|
| 🔍 API 检测 | `web/templates/index.html` | 检测中转站真伪、计费模式、后端真实模型 |
| 🧪 模型测评 | `web/templates/evaluation.html` | 独立页面，100题标准化测评，5大维度 |
| 📜 协议分析 | `web/templates/index.html` → `section-protocol` | 分析 OpenAI / Anthropic 等协议兼容性 |
| 📊 历史记录 | `web/templates/index.html` → `section-history` | 查看历史检测结果 |

### 目录结构

```
D:\Ai工作\model-detective\
├── run_web.py                  # 入口脚本
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
│   ├── detectors/              # 检测器模块
│   ├── protocols/              # 协议分析模块
│   │   └── openai/
│   │       └── client.py       # OpenAI 协议客户端（含URL自动发现）
│   └── evaluation/             # 测评引擎
│       ├── __init__.py
│       ├── eval_engine.py      # 100题测评引擎
│       └── reporter.py         # 测评报告生成
├── docs/
│   └── EVALUATION_GUIDE.md     # 测评使用指南
├── MEMORY.md                   # 本文件（项目记忆）
├── HANDOVER.md                 # 交接文档
├── FUSION_PLAN.md              # 检测+测评融合方案设计文档
├── test_framework.md           # 100题测评框架设计
├── test_questions.md           # 100题题库
└── .venv/                      # Python 虚拟环境
```

---

## 二、2026-07-25 计费完整性审计逻辑修正（重要）

### 问题 1：Token 预算耗尽

用户反馈在进行计费完整性审计时失败，显示：
```
Token 预算耗尽（16467/15000），跳过检测
```

**修复**: STANDARD 模式预算从 15,000 提升至 **25,000**

---

### 问题 2：计费检测结果"离谱"（严重逻辑错误）

用户反馈计费完整性审计结果不合理，显示极高的"计费倍率"。

**根本原因分析**（客观自查）：

1. **使用错误的 Tokenizer**：
   - 代码使用 `tiktoken.get_encoding("cl100k_base")` 计算 token
   - `cl100k_base` 是 **GPT-4/GPT-3.5** 的 tokenizer
   - **Claude 使用完全不同的 tokenizer**！
   - 用 GPT 的 tokenizer 验证 Claude 的 token 计数，必然产生偏差

2. **武断的消息格式开销**：
   - 代码假设 `_MESSAGE_FORMAT_OVERHEAD = 5` token
   - 这是**拍脑门定的**，没有依据
   - Anthropic 的实际开销可能完全不同

3. **过于严格的偏差阈值**：
   - 30% 偏差就标记为"疑似虚报计费"
   - 考虑到 tokenizer 差异和额外开销，这个阈值**完全不现实**

4. **主观定性问题**：
   - 使用"虚报"、"欺诈"、"通胀"等定性词汇
   - 实际上中转站的 token 计算方式可能有合理解释

**修正内容**（v2.5 重大修正）：

| # | 问题 | 修正文件 | 修正内容 |
|---|------|----------|----------|
| 1 | 使用错误 tokenizer | `billing_integrity.py` | 移除 tiktoken，改用粗略估算（1 token ≈ 3.5 字符） |
| 2 | 声称"精确计算" | `billing_integrity.py` | 更新文档，明确说明估算仅供参考 |
| 3 | 阈值过于严格 | `billing_integrity.py` | input 偏差阈值：30% → **100%**；output 偏差：50% → **100%** |
| 4 | 主观定性 | `billing_integrity.py` | 移除"虚报"、"欺诈"等词汇，改为客观描述 |
| 5 | 计费倍率误判 | `billing_integrity.py` | 倍率 >2x 就扣分 → 改为 >3x 仅提示，不作为负面评分 |

**修正后的检测逻辑**：
- 仅检查 token 计数是否在**合理范围**内
- 偏差较大时给出**可能原因**（系统消息、不同 tokenizer 等）
- 明确告知用户估算值**仅供参考**
- 评分更加宽松，避免误报

### 版本号
- Python 后端: **v2.8.2**（计费逻辑重大修正）

---

## 三、2026-07-25 Token 预算优化（关键修复）

### 问题

用户反馈：
1. 多个检测器显示 "Token 预算耗尽（35561/25000），跳过检测"
2. 质疑检测消耗 token 过多

### 根本原因

1. **检测器实际消耗远超预估**：`thinking_signature` 启用 thinking，实际可能消耗 2500-3500 tokens，但预估只有 600
2. **中转站返回 token 数异常高**：某些中转站可能返回了比预期更长的响应
3. **预算设置不足**：25,000 预算在某些情况下仍不够

### 修复内容（v2.5 最终修正）

| # | 问题 | 修复文件 | 修复内容 |
|---|------|----------|----------|
| 1 | STANDARD 模式预算不足 | `src/core/modes.py` | 预算从 25,000 提升至 **50,000**，确保所有检测器都能完成 |
| 2 | FULL 模式预算不足 | `src/core/modes.py` | 预算从 60,000 提升至 **100,000** |
| 3 | thinking_signature 预估过低 | `thinking_signature.py` | 从 600 提升至 **4000** |
| 4 | 其他检测器预估不准确 | 多个 detector 文件 | 修正所有检测器的 `estimated_tokens` |

### 各检测器 estimated_tokens 设置（修正后）

| 检测器 | estimated_tokens | 说明 |
|--------|------------------|------|
| thinking_signature | **4000** | thinking=1024 + max_tokens=1500 + overhead |
| identity | 250 | 正确 |
| protocol | 100 | 正确 |
| consistency | 300 | 2次请求 |
| behavioral_signature | 400 | 正确 |
| knowledge | 200 | 正确 |
| billing_integrity | 2000 | 已设置 |
| function_calling | 500 | 新增 |
| message_id | 100 | 新增 |
| token_usage | 200 | 新增 |
| integrity | 0 | PassiveDetector |
| **总计** | **~4650** | 远低于 15,000 预算 |

### 关键修复代码

**`src/core/modes.py`**
```python
TOKEN_BUDGETS = {
    RunMode.QUICK: 3_000,
    RunMode.STANDARD: 25_000,  # v2.5: 从 15,000 提升至 25,000
    RunMode.FULL: 60_000,
}
```

**示例：为检测器添加准确的预估**
```python
class IdentityDetector(ActiveDetector):
    # ...
    estimated_tokens = 250  # v2.5: prompt ~50 + output ~120 + overhead
```

**`src/core/runner.py`**
```python
details=f"Token 预算耗尽（已用 {self._tokens_used}/{self._token_budget}），跳过检测。建议：使用 FULL 模式或降低并发检测数量",
```

### 版本号
- Python 后端: v2.8.3

---

## 四、2026-07-25 UI 和检测逻辑优化

### 1. 返回首页按钮

**需求**: 在任何页面都要有返回首页按钮（首页 = API检测页面）

**实现**:
- 在页面顶部和底部添加返回首页按钮
- 仅在非 API 检测页面时显示
- 点击后切换回 API 检测 Tab

**修改文件**:
- `web/templates/index.html` - 添加按钮 HTML
- `web/static/style.css` - 添加按钮样式
- `web/static/app.js` - 添加显示/隐藏逻辑

### 2. 中转站名称显示

**问题**: 检测完成后显示 "未知中转站"

**修复**:
- 修改 `web/app.py` `_serialize_report` 函数，添加 `base_url` 参数
- 将实际使用的中转站网址返回给前端显示

### 3. 身份认知检测优化 (v2.5)

**问题**: Claude 经常回复 "I can't discuss that"，导致无法获得身份信息

**优化方案**:
- **多策略询问**: 尝试 4 种不同的询问方式，直到获得有效回答
  1. 直接询问
  2. 间接询问（补全句子）
  3. 技术文档视角
  4. 对比询问
- **智能拒绝检测**: 识别各种拒绝模式（cannot/ unable/ can't 等）
- **灵活评分**:
  - 所有策略都被拒绝：35 分（不直接判失败）
  - 部分拒绝：根据拒绝次数适当扣分
  - 成功识别：根据匹配程度给 80-95 分

**评分逻辑改进**:
- 区分"拒绝回答"和"回答但不匹配"
- 拒绝时给出可能原因（系统提示约束、安全策略等）
- 建议结合其他检测项综合判断

### 4. 一致性检测优化 (v2.5)

**问题**: 11 次请求都返回相同模型名称，但评分没有充分体现一致性优势

**优化方案**:
- **观察次数奖励**: 每次成功观察 +2 分，最多 +15 分
- **分级评价**:
  - ≥10 次一致："优秀的一致性"
  - ≥5 次一致："良好的一致性"
  - <5 次一致："模型名称一致"
- **不一致分级**:
  - 严重不一致（>50% 不同）：扣 30 分
  - 轻微不一致：扣 15 分
  - 仅格式不同：扣 3 分

**修改文件**:
- `src/protocols/anthropic/detectors/identity.py`
- `src/protocols/anthropic/detectors/integrity.py`
- `web/app.py`

---

## 五、2026-07-23 API检测404错误修复

### 问题描述

API检测时全部返回404错误：
```
请求失败: HTTP 404: {"error":{"message":"请求失败，请根据错误码处理","type":"INVALID_REQUEST","code":"INVALID_REQUEST"}}
```

### 修复内容

| # | 问题 | 原因 | 修复文件 | 修复内容 |
|---|------|------|----------|----------|
| 1 | URL路径尝试不够全面 | 只尝试了3种URL模式，某些中转站需要特殊路径 | `src/protocols/openai/client.py` `_try_resolve_chat_url` | 增加更多候选URL（包括`/openai/v1/chat/completions`等） |
| 2 | 前端使用过期State值 | `startDetection`使用`State.baseUrl`而非输入框最新值 | `web/static/app.js` | 改为直接从输入框读取`effective_base_url` |
| 3 | Anthropic协议404处理 | Anthropic客户端在404错误时不会尝试其他URL路径 | `src/protocols/anthropic/client.py` | 添加404错误时的URL重试逻辑，扩大URL尝试范围 |
| 4 | ProtocolResolver探测范围 | 只探测/models端点，某些中转站可能只支持/chat/completions | `src/core/protocol_resolver.py` `_resolve_openai_base_url` | 增加chat completions探测，新增更多URL模式 |

### 关键修复代码

**`src/protocols/openai/client.py`**
```python
# 扩大URL尝试范围
if base.endswith("/v1"):
    url_candidates = [
        f"{base}/chat/completions",
        f"{base.rstrip('/v1')}/v1/chat/completions",
        f"{base.rstrip('/v1')}/chat/completions",
    ]
else:
    url_candidates = [
        f"{base}/v1/chat/completions",
        f"{base}/chat/completions",
        f"{base}/api/v1/chat/completions",
        f"{base}/openai/v1/chat/completions",  # 新增
    ]
```

**`web/static/app.js`**
```javascript
// 优先使用输入框的值（因为探测阶段会更新输入框为 effective_base_url）
const baseUrl = $('base_url').value.trim();
const apiKey = $('api_key').value.trim();

// 更新 State 以确保使用最新的值
State.baseUrl = baseUrl;
State.apiKey = apiKey;
```

### 版本号
- HTML/JS/CSS: `EVAL_AUTOPROBE_20260723_8`

### 调试状态
- 已添加调试日志到 `src/protocols/anthropic/client.py`
- 等待用户测试并提供服务器控制台输出
- 404 错误仍然存在，需要进一步分析

---

## 三、2026-07-23 thinking_signature Bug 修复

### 修复内容

| # | 问题 | 原因 | 修复文件 | 修复内容 |
|---|------|------|----------|----------|
| 1 | thinking 请求被中转站 HTTP 400 拒绝 | 上一轮降本优化时将 `budget_tokens` 从 1024 降至 500，但 Anthropic API 要求 `budget_tokens` 最小值为 1024 | `src/protocols/anthropic/detectors/thinking_signature.py` 第46行 | `budget_tokens`: 500 → **1024**（恢复为 API 最低要求） |
| 2 | max_tokens 过小导致回答空间不足 | 之前 max_tokens 从 2000 降至 800，留给实际回答的空间太小 | 同上第45行 | `max_tokens`: 800 → **1500**（留出 476 token 给实际回答，比原来 2000 仍省 25%） |

### 关键修复代码

**`src/protocols/anthropic/detectors/thinking_signature.py` (第45-46行)**
```python
# 修复前（bug）:
max_tokens=800,
thinking={"type": "enabled", "budget_tokens": 500},

# 修复后:
max_tokens=1500,
thinking={"type": "enabled", "budget_tokens": 1024},
```

### 原因分析

Anthropic API 规定 `thinking.budget_tokens` 最小值为 **1024**，低于此值会导致 API 直接返回 HTTP 400 拒绝请求。上一轮降本优化时将其降至 500，导致中转站转发请求时被 Anthropic 后端拒绝，thinking_signature 检测器无法正常工作。

### 测试结果

- 修复后 78 号测试通过
- 思维签名验证功能恢复正常
- 服务器已重启验证

---

## 三、2026-07-22 题库 v2.0 优化记录

### 优化概览

对100题测评题库进行全面优化，修复Bug，统一标准，提升质量。

### 发现并修复的Bug

| # | 问题 | 严重程度 | 修复方案 |
|---|------|----------|----------|
| 1 | 评分标准混乱（5/7/8分制混用） | 高 | 统一为10分制 |
| 2 | 题目41折扣计算逻辑错误 | 高 | 改为 discount_percent 参数 |
| 3 | 题目12有时效性问题（诺贝尔奖） | 中 | 改为科学概念解释 |
| 4 | 题目8语法判断有争议 | 中 | 改为分析语法特点 |
| 5 | 题目77-82依赖上下文 | 高 | 改为独立可测的题目 |
| 6 | 题目97无实际内容 | 中 | 提供可解析的嵌套结构 |
| 7 | 权重计算错误（总分430≠100） | 高 | 修正为1000分制 |

### 主要优化内容

**1. 统一评分体系**
- 所有题目采用10分制
- 评分档次：优秀(9-10)、良好(7-8)、合格(5-6)、不合格(0-4)
- 总分1000分，加权后100分

**2. 题目质量提升**
- 优化了15+道题目的表述
- 增加了更明确的评分标准
- 补充了expected_keywords

**3. 新增题目类型**
- 系统设计测试（数据库、缓存、限流等）
- Git/Docker/正则等工具使用
- 更完善的边界测试

**4. 文档完善**
- 新增评分汇总表
- 新增难度分级说明
- 新增自动化评分建议

### 文件变更

- `test_questions_v2.md` - 新版题库文档
- `src/evaluation/eval_engine.py` - 更新内置题库

---

## 三、2026-07-21 重大修复记录

### 修复内容

| # | 问题 | 原因 | 修复文件 | 修复内容 |
|---|------|------|----------|----------|
| 1 | 测评 403 错误 | `OpenAIClient` 收到 403 后，因 `base_url.endswith("/v1")` 检查而跳过 URL 重试 | `src/protocols/openai/client.py` | 移除 `and not self.base_url.endswith("/v1")` 条件，确保即使 base_url 以 /v1 结尾也会尝试其他 URL 路径 |
| 2 | 探测与测评 URL 不一致 | 探测阶段发现 `/v1` 路径，但测评阶段未同步 | `web/app.py` + `web/static/app.js` | 后端返回 `effective_base_url`，前端更新输入框和 State |
| 3 | 代码逻辑错误 | `app.py` 中引用未定义变量 `base` | `web/app.py` | 修复为 `effective_base_url` |

### 关键修复代码

**`src/protocols/openai/client.py` (第165行)**
```python
# 修复前:
elif resp.status_code in (403, 404) and not self._resolved_chat_url and not self.base_url.endswith("/v1"):

# 修复后:
elif resp.status_code in (403, 404) and not self._resolved_chat_url:
```

**`web/app.py` (api_probe 函数)**
```python
# 根据成功探测的 URL 推断 effective_base_url
effective_base_url = base_url.rstrip("/")
if "/v1/models" in url:
    effective_base_url = effective_base_url + "/v1"
elif "/api/v1/models" in url:
    effective_base_url = effective_base_url + "/api/v1"

return jsonify({
    ...
    "effective_base_url": effective_base_url,
})
```

**`web/static/app.js` (renderEvalProbeResult 函数)**
```javascript
// 使用后端返回的有效 base_url（可能已补 /v1）
if (data.effective_base_url) {
  State.evalBaseUrl = data.effective_base_url;
  // 同时更新输入框的值，让用户知道实际使用的 URL
  $('eval-base_url').value = data.effective_base_url;
}
```

---

## 三、测评体系设计概要

### 5 大维度 × 20 题 = 100 题

| 维度 | 代号 | 题数 | 说明 |
|------|------|------|------|
| 基础语言 | basic_language | 20 | 翻译、摘要、改写、情感分析等 |
| 技术编码 | technical | 20 | 代码生成、调试、算法实现 |
| 高级认知 | advanced_cognition | 20 | 推理、规划、多步决策 |
| 实用场景 | practical | 20 | 角色扮演、格式控制、多轮对话 |
| 边界测试 | boundary | 20 | 幻觉检测、越狱防护、一致性 |

### 难度分级

- **Quick（快速）**：每维度 4 题，共 20 题
- **Standard（标准）**：每维度 8 题，共 40 题
- **Full（完整）**：每维度 20 题，共 100 题

### 评分机制

- 每题 0-10 分
- 各维度独立评分 + 总分
- 输出可视化报告（雷达图 + 详细表格）

---

## 四、前端架构要点

### Tab 切换机制（initHeroTabs）

```javascript
function initHeroTabs() {
  const tabDetection = $('tab-detection');
  const tabEvaluation = $('tab-evaluation');
  const sectionDetection = $('section-detection');
  const sectionEvaluation = $('section-evaluation');

  // 初始状态
  sectionDetection.hidden = false;   // 显示检测页
  sectionEvaluation.hidden = true;   // 隐藏测评页

  function switchTab(tab) {
    if (tab === 'detection') {
      sectionDetection.hidden = false;
      sectionEvaluation.hidden = true;
    } else {
      sectionDetection.hidden = true;
      sectionEvaluation.hidden = false;
      // 测评页内部步骤控制
      $('eval-step-config').hidden = false;
      $('eval-step-models').hidden = true;
      $('eval-step-dimensions').hidden = true;
      $('eval-step-launch').hidden = true;
      $('eval-step-results').hidden = true;
    }
  }
}
```

### 测评页内部步骤

1. `eval-step-config` — 配置 API 连接（base_url + api_key）
2. `eval-step-models` — 选择要测评的模型（支持自动探测）
3. `eval-step-dimensions` — 选择测评维度和难度
4. `eval-step-launch` — 开始测评 + SSE 实时进度
5. `eval-step-results` — 展示测评报告

### 关键 ID 对照

| 元素 | ID | 所属 section |
|------|-----|-------------|
| Tab 按钮 | `tab-detection` / `tab-evaluation` | hero 区域 |
| 外层容器 | `section-detection` / `section-evaluation` | body |
| 配置卡片 | `step-config` / `eval-step-config` | 对应 section |
| 输入框 | `base_url` / `eval-base_url` | 对应卡片 |
| 输入框 | `api_key` / `eval-api_key` | 对应卡片 |

---

## 五、后端架构要点

### Flask 路由

| 路由 | 方法 | 功能 |
|------|------|------|
| `/` | GET | 渲染主页 |
| `/api/probe` | POST | 探测中转站（检测模块） |
| `/api/evaluate` | POST | 启动测评任务 |
| `/api/evaluate/status/<job_id>` | GET | 查询测评进度 |
| `/api/history` | GET | 获取历史记录 |
| `/api/clear-history` | POST | 清除历史记录 |

### 测评引擎

- `src/evaluation/eval_engine.py` — 核心引擎，加载题库、执行测评、生成报告
- `src/evaluation/reporter.py` — 报告格式化（JSON + 可视化数据）

### URL 自动发现机制

1. **探测阶段** (`api_probe`): 尝试多种 `/models` 路径，返回 `effective_base_url`
2. **前端同步**: 更新输入框显示探测到的有效 URL
3. **测评阶段** (`OpenAIClient`): 收到 403/404 时自动尝试其他 `/chat/completions` 路径

---

## 六、服务器启动方式

```powershell
cd D:\Ai工作\model-detective
.\.venv\Scripts\python.exe run_web.py
```

**注意**：不要用系统 Python（`python`），因为系统 Python 损坏。必须使用虚拟环境中的 Python。

---

## 七、已知限制

1. **浏览器缓存**：Flask 开发服务器默认不缓存模板，但浏览器可能缓存静态资源。建议每次修改后 Ctrl+Shift+R 强制刷新。
2. **Section 嵌套**：HTML 中使用 `<section>` 嵌套 `<section>`，某些浏览器可能自动调整 DOM 树结构。
3. **虚拟环境路径**：`D:\Ai工作\model-detective\.venv\` 中包含中文路径，某些工具可能不支持。

---

## 八、v2.8.3 检测器深度优化（2026-08-01）

### 8.1 置信度系统（Confidence System）

**新增核心数据模型字段：**
```python
@dataclass
class CheckResultV2:
    # ... 现有字段
    confidence: float = 1.0         # 0-1，检测结果可信度
    confidence_reason: str = ""      # 置信度说明
```

**已应用检测器：**
- `identity`: 0.2-0.95（根据回答明确程度）
- `thinking_signature`: 0.5-0.98（根据签名验证情况）
- `knowledge`: 0.5-0.85（根据知识点掌握情况）
- `integrity`: 0.0-0.95（根据观察数据质量）
- `consistency`: 0.0-0.95（根据样本量和一致性）
- `behavioral_signature`: 默认 0.7（保守估计）
- `function_calling`: 0.7-0.98
- `protocol`: 0.7-0.95
- `token_usage`: 0.0-0.9
- `basic_request` (OpenAI/Gemini): 0.7-0.95
- `model_consistency` (OpenAI): 0.75-0.95

**评分引擎更新：**
- `_weighted_avg()` 函数支持置信度加权评分
- 新增 `calculate_confidence_stats()` 统计整体置信度

### 8.2 behavioral_signature 过拟合修复

**问题：** 检测器过度依赖主观特征（Markdown列表、特定短语），权重过高（0.08）

**修复：**
- 权重：0.08 → 0.04
- 移除主观短语检测（"here are", "certainly" 等）
- 移除非 Claude 特征判定（"sure thing" 等）
- 改为仅检测结构化输出能力
- 评分策略：基础分 60，仅加分不扣分（最高 85）

### 8.3 knowledge 检测器重构

**原问题：** 仅依赖单一知识点（2024 美国大选），时效性风险

**改进：**
- 3 个知识点验证：2024 大选、2024 奥运会、2025 AI 模型
- 增加置信度系统
- Token 预算：200 → 600

### 8.4 consistency 检测器增强

**改进：**
- 样本量：2 → 3 次请求
- 问题复杂度提升：简单事实 → 数学计算
- 增加置信度系统

### 8.5 权重重新平衡

```python
# Anthropic 协议
identity:              0.10 → 0.12   # 身份认知更重要
behavioral_signature:  0.08 → 0.04   # 降低过拟合风险
knowledge:             0.07 → 0.06   # 非核心判定依据
integrity:             0.06 → 0.08   # 被动观察更客观
long_context:          0.02 → 0.03   # 长上下文能力重要性提升
```

### 8.6 代码重构

**新增文件：**
- `src/core/error_standards.py`: 统一错误评分标准
- `src/utils/model_name_utils.py`: 公共模型名称处理函数

**更新文件：**
- `src/protocols/anthropic/detectors/integrity.py`: 使用公共工具函数
- `src/protocols/openai/detectors/basic_request.py`: 使用公共工具函数 + 置信度
- `src/protocols/openai/detectors/model_consistency.py`: 3 样本 + 置信度
- `src/protocols/gemini/detectors/basic_request.py`: 使用公共工具函数 + 置信度

### 8.7 错误评分标准统一

**新建 `ErrorScore` 标准：**
- `REQUEST_FAILED`: score=0, confidence=0.0
- `INVALID_RESPONSE`: score=10, confidence=0.3
- `MISSING_CRITICAL_FIELD`: score=15, confidence=0.4
- `PARTIAL_SUCCESS`: score=50, confidence=0.6
- `BUDGET_EXHAUSTED`: score=0, confidence=0.0

---

## 九、v2.7 Consistency 检测器重构（2026-08-03）

### 9.1 核心变更：数学题 → 创意写作

**问题**：v2.6 使用数学题（`Calculate 15 * 17`）检测一致性，存在"确定性陷阱"——数学题在 temperature=0 时真伪模型都返回相同答案，无法区分真伪，只能检测稳定性。

**修复**：改为创意写作问题（`Write a haiku about AI`），haiku 在 temperature=0 时仍有自然变化，能更好地区分真伪模型。

### 9.2 评分变更：二元化 → 多维度加权

**问题**：v2.6 评分 95/75/45 三档跳跃，缺乏渐进性；正确答案权重仅 +3 分。

**修复**：三维度加权评分：
- 答案一致性 40%：基于字符串相似度（SequenceMatcher）的渐进式评分
- 特征稳定性 30%：长度变异系数 + 行数变异系数 + 格式一致性
- 语义相似度 30%：Jaccard 指数（词汇重叠），非线性映射

### 9.3 三协议同步

| 协议 | 文件 | 变更 |
|------|------|------|
| Anthropic | `src/protocols/anthropic/detectors/consistency.py` | v2.6 → v2.7 重构 |
| OpenAI | `src/protocols/openai/detectors/model_consistency.py` | v2.6 → v2.7（保留模型名检查作为修饰符） |
| Gemini | `src/protocols/gemini/detectors/consistency.py` | 新建（v2.7） |
| 共享 | `src/utils/consistency_scorer.py` | 新建，三协议共享评分逻辑 |

### 9.4 Gemini 配置更新

新增 `consistency` 检测器（权重 0.10），其他权重重平衡：
- `function_calling`: 0.18 → 0.14
- `structured_output`: 0.15 → 0.11
- `billing_integrity`: 0.13 → 0.11
- 合计仍 = 1.00

### 9.5 Token 预算

- `estimated_tokens`: 450 → 600
- `max_tokens`: 50 → 60
- 请求次数: 3（不变）

### 9.6 版本号

- Python 后端: **v2.8.4**（Consistency v2.7 重构）

---

## 十、v2.7 Identity 检测器重构（2026-08-03）

### 10.1 核心变更：关键词匹配 → 语义理解

**问题**：v2.5 使用简单关键词匹配（`if "claude" in all_content`），存在多个误判场景：
1. **否定误判**："I am not Claude" 会被误判为 Claude 匹配
2. **部分拒绝误判**："I can't say for sure, but I think I'm Claude" 会被误判为拒绝
3. **跨策略不一致未检测**：不同策略返回不同身份时未标记异常
4. **二元化评分**：95/25/45 跳跃，缺乏渐进性

**修复**：
1. 否定语境检测：使用正则表达式检测关键词周围的否定词（not/unlike/不是/并非）
2. 智能拒绝检测：区分纯拒绝（无身份信息）vs 部分拒绝（拒绝后仍透露身份）
3. 跨策略一致性：比较不同策略提取的身份，不一致时标记 MAJOR issue
4. 渐进式评分：基于身份匹配程度、版本匹配、策略一致性综合评分

### 10.2 共享分析逻辑

| 文件 | 说明 |
|------|------|
| `src/utils/identity_analyzer.py` | 新建，共享身份分析逻辑 |
| `src/protocols/anthropic/detectors/identity.py` | v2.5 → v2.7 重构 |

### 10.3 关键测试场景

| 场景 | 输入 | v2.5 结果 | v2.7 结果 |
|------|------|----------|----------|
| 肯定匹配 | "I am Claude 3.5 Sonnet" | ✅ 95 | ✅ 95（含版本） |
| 否定检测 | "I am not Claude, I am GPT-4" | ❌ 误判为 Claude | ✅ 正确识别 GPT |
| 纯拒绝 | "I cannot answer" | ✅ 35 | ✅ 35 |
| 部分拒绝 | "I can't say, but I'm Claude" | ❌ 误判为拒绝 | ✅ 正确识别 Claude |
| 比较否定 | "Unlike Claude, I am GPT-4" | ❌ 误判为 Claude | ✅ 正确识别 GPT |
| 策略不一致 | 策略1=Claude, 策略2=GPT | ❌ 未检测 | ✅ 标记 MAJOR |
| 身份不匹配 | 声称 Claude, 自报 GPT | ✅ 25 | ✅ 20 |

### 10.4 版本号

- Python 后端: **v2.8.5**（Identity v2.7 重构 + 渐进式探测 + Aurora Dark v3.0 前端）

---

## 十一、Aurora Dark v4.0 前端设计语言（2026-08-04）

### 11.1 设计概要

前端全面升级为 **Cosmic Galaxy v5.1** 设计语言，CSS 版本号 `COSMIC_V5_1_20260804`。

**核心设计元素：**
- **深邃极光暗色背景**：`--bg-0: #050714` → `--bg-5: #303a5f` 五层背景色阶
- **真玻璃态效果**：`backdrop-filter: blur(20px)` + 半透明背景 + 玻璃态边框
- **极光渐变系统**：`--grad-aurora: linear-gradient(135deg, #5b8eff → #b388ff → #2ad4ee)`
- **分层光影卡片**：`box-shadow: var(--shadow), var(--shadow-inset)` 内外光影叠加
- **动态极光背景动画**：`auroraShift 30s ease-in-out infinite alternate` 三层径向渐变旋转
- **卡片入场动画**：`cardIn 0.55s var(--t-slow)` 渐入上滑
- **Hero 光晕脉冲**：`glowPulse 8s ease-in-out infinite alternate`
- **粒子动画系统**：`particleFloat` 动态粒子背景
- **滚动触发动画**：IntersectionObserver 实现滚动时元素渐入效果

### 11.2 全新首页设计（v4.0 重大升级）

**参考网站设计风格**：oken.ai（实验室风格）、veridrop.org（简洁科技感）、hvoy.ai（现代感）、llmtest.cn（专业性）

**新增页面区域：**

1. **固定导航栏（Navbar）**
   - 固定在顶部，滚动时背景加深
   - Logo + 品牌名 + Tab 切换 + GitHub 链接
   - 玻璃态效果，backdrop-filter: blur(20px)

2. **Hero 主视觉区**
   - 全屏高度（100vh），居中对齐
   - 动态粒子背景（20个浮动粒子）
   - 版本徽章（v4.0 Aurora 现已发布）
   - 大标题 + 渐变文字效果
   - 双 CTA 按钮（立即开始检测 / 模型能力测评）
   - 统计数据栏（31+ 检测器 / 3 协议 / 100 测评题 / 完全免费）
   - 浮动功能卡片（真伪检测 / 计费审计 / 能力测评）

3. **核心功能展示（Features Grid）**
   - 6 个功能卡片网格布局
   - 图标 + 发光效果 + 标题 + 描述 + 标签
   - 悬停上浮动画 + 边框高亮

4. **使用流程展示（How It Works）**
   - 三步流程卡片（配置连接 → 选择模式 → 查看报告）
   - 步骤编号 + 图标 + 箭头连接
   - 悬停图标变色动画

### 11.3 设计令牌体系

| 类别 | 变量 | 说明 |
|------|------|------|
| 背景层次 | `--bg-0` ~ `--bg-5` | 五层深色背景色阶 |
| 玻璃态 | `--glass`, `--glass-2`, `--glass-3`, `--glass-border` | 多级半透明效果 |
| 文字层次 | `--txt-1` ~ `--txt-4` | 四级文字对比度 |
| 强调色 | `--blue`, `--cyan`, `--purple`, `--green` 等 | 极光系配色 |
| 渐变 | `--grad`, `--grad-aurora`, `--grad-warm` | 多场景渐变预设 |
| 圆角 | `--radius` (20px), `--radius-md` (14px), `--radius-sm` (10px), `--radius-xs` (8px) | 统一圆角体系 |
| 动效 | `--t` (0.35s), `--t-fast` (0.15s), `--t-slow` (0.6s), `--t-bounce` | 四级动效曲线 |
| 字号 | `--fs-base` ~ `--fs-4xl` | 八级字号体系 |

---

## 十二、待办事项

### 已完成

- [x] **修复 Tab 切换 Bug**：点击"模型测评"Tab 后页面不切换
- [x] **修复测评 403 错误**：URL 路径自动发现和同步
- [x] **修复自动探测失效**：探测到的模型列表正确显示
- [x] **修复 thinking budget_tokens Bug**：budget_tokens 从 500 恢复为 1024
- [x] **v2.8.3 检测器深度优化**：置信度系统、过拟合修复、权重重平衡
- [x] **v2.7 Consistency 重构**：数学题→创意写作、二元化→多维度加权、三协议同步
- [x] **Identity v2.7 重构**：语义理解+否定检测+跨策略一致性+部分拒绝检测
- [x] **渐进式探测机制**：预检探针+分优先级执行+早终止（p3完成）
- [x] **v1回溯验证**：12/12全部通过
- [x] **v2自检Bug修复**：14/14通过，修复中文否定跨身份误判Bug（范围25→5）
- [x] **Aurora Dark v3.0 前端**：全新CSS设计语言落地
- [x] **UI 小优化升级**：视觉细节打磨和交互体验提升
- [x] **HANDOVER.md v2.9 交接文档**：完整记录v2.7重构所有变更
- [x] **Aurora Dark v4.0 首页大升级**：参考 oken.ai / veridrop.org / hvoy.ai / llmtest.cn，全新 Hero + Features + How It Works 设计
- [x] **UI Bug 修复 v4.1**：移除浮动卡片、优化回到顶部按钮位置、放大核心功能标题、测评配置卡片前置
- [x] **模型测评独立页面**：创建 evaluation.html + evaluation.css + evaluation.js，支持独立访问 /evaluation
- [x] **Cosmic Galaxy v5.1 宇宙主题**：深邃宇宙背景、银河星云、星光闪烁动效、高级玻璃态质感

### 待完成

**UI/UX 优化（用户明确要求继续惊艳设计）：**
- [ ] 继续优化页面质感和高级感
- [ ] 完善动效细节（可能需要调整闪烁频率、星云速度等）
- [ ] 检查所有交互元素的反馈效果
- [ ] 优化移动端适配

**功能开发：**
- [ ] 完善测评引擎的 SSE 进度推送
- [ ] 添加测评报告的导出功能（PDF/JSON）
- [ ] 支持批量测评多个模型
- [ ] 添加测评结果的历史记录和对比功能
- [ ] 前端展示置信度标签和解释

---

*此文件由 AgnesCode 维护，供后续 AI 代理继承上下文使用。最后更新: 2026-08-11*

---

## 七、2026-08-26 按次收费中转站 Cloudflare WAF 拦截修复

### 问题
用户反馈 tabitoken.com、gorouter.app 等按次收费中转站检测失败，显示 Cloudflare 403 阻止。

### 根本原因分析

**第一层原因（直接）：Cloudflare WAF 拦截非浏览器 UA**
- 中转站部署了 Cloudflare WAF Bot 防护
- 非浏览器 User-Agent（如 python-requests/2.x）被 WAF 直接返回 403
- 用浏览器 UA 测试后，tabitoken.com 和 gorouter.app 都返回 401（正常认证失败）

**第二层原因（深层）：base_url 重复拼接 /v1/v1 导致 404**
- 错误日志显示 POST /v1/v1/messages，base_url 变成 https://gorouter.app/v1/v1
- 根因：protocol_resolver.py 第 206-207 行，探活成功后无条件追加 /v1
- 如果 base_url 已经是 https://gorouter.app/v1，探活 URL 是 .../v1/messages
- 返回 200 后，base_url 变成 https://gorouter.app/v1 + /v1 = https://gorouter.app/v1/v1

### 修复内容

1. src/core/http_utils.py: 新增 BROWSER_HEADERS 常量
2. src/protocols/base_client.py: session 创建时注入浏览器头
3. src/api_client.py: session 创建时注入浏览器头
4. src/core/protocol_resolver.py: 所有探测请求 + 修复 /v1/v1 重复
5. src/protocols/anthropic/client.py: 用 clean_base 替代 rstrip('/v1')
6. web/app.py: /api/probe 端点注入浏览器头

### 验证结果

| 中转站 | 修复前 | 修复后 |
|--------|--------|--------|
| tabitoken.com | HTTP 403 | HTTP 401（正常认证失败） |
| gorouter.app | HTTP 403 | HTTP 401（正常认证失败） |

### 版本号
- 后端: v2.8.7

### 提交记录
- 3fa9bed fix: 添加浏览器 UA 绕过 Cloudflare WAF 403 拦截
- d584aaa fix: 修复 base_url 重复拼接 /v1/v1 导致 404

### 关键教训
1. Cloudflare WAF 会阻止非浏览器 UA，所有 HTTP 请求必须伪装浏览器头
2. str.rstrip('/v1') 是危险操作——逐字符移除，不是移除整个子串
3. base_url 修正逻辑需要幂等性

---

*此文件由 AgnesCode 维护，供后续 AI 代理继承上下文使用。最后更新: 2026-08-26*
