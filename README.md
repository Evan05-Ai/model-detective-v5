# Model Detective — API 中转站检测 & 模型能力测评

> 🔍 一站式 AI API 中转站检测工具：验证模型真伪、计费诚信、协议合规，并提供标准化模型能力测评。

<p align="center">
  <strong>Cosmic Galaxy v5.1</strong> · 前端 · 后端 v2.9.1
</p>

<p align="center">
  <a href="https://detect.model-detective.online" target="_blank">🌐 在线访问: detect.model-detective.online</a>
</p>

---

## 🚀 快速启动

```bash
# 1. 克隆仓库
git clone https://github.com/<your-username>/model-detective-v5.git
cd model-detective-v5

# 2. 创建虚拟环境
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 启动服务
python run_web.py
```

浏览器访问 `http://localhost:5000`

> 💡 Windows 服务部署（nssm + Cloudflare Tunnel）见 [DEPLOY_CLOUDFLARE_TUNNEL.md](DEPLOY_CLOUDFLARE_TUNNEL.md)

---

## 📋 两大核心功能

### 1. 🔍 API 中转站检测

验证中转站提供的模型是否真实、计费是否诚信、协议是否合规。

**支持的协议**：OpenAI Chat Completions / Anthropic Messages / Gemini GenerateContent

**检测维度（3D 评分体系）**：

| 维度 | 说明 | 关键检测项 |
|------|------|-----------|
| **真伪** | 模型身份验证 | 思维签名、身份认知、行为指纹、消息ID规范 |
| **能力** | 模型能力验证 | 函数调用、结构化输出、长上下文、PDF处理 |
| **合规** | 协议计费合规 | 协议规范、Token计费、计费完整性审计 |

**检测引擎**：
- **Consistency v2.7**：多维度加权评分，温度=0稳定性验证
- **Identity v2.7**：语义理解 + 否定检测，深度身份认知分析
- **渐进式探测**：预检探针 → 分优先级执行 → 早终止优化

**检测模式**：

| 模式 | 耗时 | 检测器数 | 适用场景 |
|------|------|----------|----------|
| Quick | ~15s/模型 | 3 | 快速验真 |
| Standard | ~40s/模型 | 7 | 均衡覆盖（推荐） |
| Full | ~70s+/模型 | 8+ | 深度审计 |

**输出**：HTML 检测报告（含三维得分、判定、后端来源推断、计费审计详情）

### 2. 🧪 模型能力测评

对任意模型进行标准化、多维度的能力评估。

**测评维度**（5维度，100题）：

| 维度 | 题数 | 占比 | 内容 |
|------|------|------|------|
| 基础语言 | 20 | 20% | 语义歧义、语境推断、文化理解、逻辑推理 |
| 技术能力 | 25 | 25% | 代码生成/理解、算法、数据结构、数学、API设计 |
| 高级认知 | 25 | 25% | 多步推理、抽象思维、创意表达、伦理分析 |
| 实用能力 | 20 | 20% | 指令遵循、上下文管理、错误处理、风格适应 |
| 边界鲁棒 | 10 | 10% | 矛盾信息、误导性问题、安全边界、压力测试 |

**测评模式**：

| 模式 | 题数 | 耗时/模型 | 适用场景 |
|------|------|-----------|----------|
| 精简版 | 20 | ~2分钟 | 快速预览 |
| 标准版 | 40 | ~5分钟 | 均衡覆盖 |
| 完整版 | 100 | ~12分钟 | 全面深入 |

**输出**：单模型详细报告 + 多模型对比表格（含排名、维度雷达图数据、JSON导出）

---

## 📁 项目结构

```
model-detective/
├── src/
│   ├── core/                       # 核心检测引擎
│   │   ├── models.py               # 数据模型
│   │   ├── runner.py               # 两阶段并行调度器
│   │   ├── scorer.py               # 加权评分引擎
│   │   ├── modes.py                # Quick/Standard/Full 模式配置
│   │   ├── protocol_resolver.py    # 自动协议识别
│   │   ├── detector_base.py        # 检测器基类
│   │   ├── http_utils.py           # HTTP 工具
│   │   ├── sse_parser.py           # SSE 流式解析
│   │   └── error_standards.py      # 错误标准
│   ├── protocols/
│   │   ├── base_client.py          # 客户端基类
│   │   ├── openai/                 # OpenAI 协议（客户端 + 10检测器）
│   │   ├── anthropic/              # Anthropic 协议（客户端 + 14检测器）
│   │   └── gemini/                 # Gemini 协议（客户端 + 7检测器）
│   ├── evaluation/                 # 模型能力测评模块
│   │   ├── eval_engine.py          # 测评引擎（100题 + 评分器）
│   │   └── reporter.py             # JSON/HTML 报告生成
│   ├── baselines/                  # 基线检测报告管理
│   ├── utils/                      # Token计数、价格数据库、稳定性分析
│   ├── reports/                    # HTML 报告模板
│   ├── signatures.py               # 模型指纹库
│   ├── reporter.py                 # 报告序列化
│   └── api_client.py               # API 客户端
├── web/
│   ├── app.py                      # Flask 后端（检测 + 测评 API）
│   ├── templates/
│   │   ├── index.html              # 首页（Cosmic Galaxy v5.1）
│   │   └── evaluation.html         # 测评独立页面
│   └── static/
│       ├── app.js                  # 首页前端逻辑
│       ├── evaluation.js           # 测评页前端逻辑
│       ├── evaluation.css          # 测评页样式
│       ├── starfield.js            # 粒子动画
│       └── style.css              # Cosmic Galaxy 深色主题 UI
├── tests/                          # 单元测试
│   ├── test_core/                  # 核心引擎测试
│   ├── test_openai/                # OpenAI 协议测试
│   ├── test_anthropic/             # Anthropic 协议测试
│   └── test_gemini/                # Gemini 协议测试
├── docs/
│   ├── BILLING_INTEGRITY_FIX_2026-08-11.md  # 计费检测修复报告
│   ├── EVALUATION_GUIDE.md         # 测评使用指南
│   └── WORK_LOG_2026-08-10.md      # 部署工作日志
├── scripts/                        # 辅助脚本（PDF 样本生成、计费审计）
├── config.example.json             # 配置示例
├── detect.py                       # CLI 检测入口
├── run_web.py                      # Python 启动入口
├── restart_service.bat             # Windows 服务重启（nssm，需管理员）
├── install_flask_service.bat       # Windows 服务安装（nssm）
├── start_named_tunnel.bat          # Cloudflare 命名隧道手动启动
├── requirements.txt                # 依赖列表
├── pytest.ini                      # 测试配置
└── README.md                       # 本文件
```

---

## 🔌 API 端点

### 页面路由

| 路由 | 说明 |
|------|------|
| `GET /` | 首页 — API 检测 |
| `GET /evaluation` | 模型测评页面 |
| `GET /health` | 健康检查 |

### 检测 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/probe` | POST | 探测中转站可用模型（多URL回退 + 双Auth头） |
| `/api/detect` | POST | 提交检测任务 |
| `/api/status/<job_id>` | GET | 轮询检测状态（SSE + JSON） |
| `/api/report/<job_id>` | GET | 获取完整检测报告 |
| `/api/providers` | GET | 预置服务商列表（15+ 厂商） |

### 测评 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/evaluate` | POST | 提交测评任务 |
| `/api/evaluate/status/<job_id>` | GET | 轮询测评状态（SSE + JSON） |

### 请求示例

```json
// POST /api/detect
{
  "base_url": "https://api.example.com/v1",
  "api_key": "sk-...",
  "models": ["gpt-4o", "claude-sonnet-4"],
  "mode": "standard",
  "protocol": "auto"
}

// POST /api/evaluate
{
  "base_url": "https://api.example.com/v1",
  "api_key": "sk-...",
  "models": ["gpt-4o", "claude-sonnet-4"],
  "difficulty": "standard",
  "dimensions": ["basic_language", "technical", "advanced_cognition", "practical", "boundary"]
}
```

---

## 🎨 Cosmic Galaxy 前端特性

- **全屏 Hero 区**：粒子动画 + 浮动卡片
- **鼠标追踪光晕**：feature-card / step-card / dimension-card 的 CSS 变量驱动
- **滚动进度条**：顶部固定，实时显示阅读进度
- **6 功能卡片网格**：响应式布局
- **三步流程展示**：可视化操作流程
- **触摸设备优化**：禁用光晕、增大点击区域（44px）、阻止双击缩放
- **移动端适配**：粒子减量、步骤箭头隐藏、卡片内边距缩小
- **性能优化**：navbar 滚动使用 `requestAnimationFrame` + CSS 类切换

---

## 📊 评分体系

### 检测评分（3D 加权）

| 维度 | 评分组成 |
|------|---------|
| 真伪得分 | 身份认知 + 行为指纹 + 思维签名 + 消息ID规范 |
| 能力得分 | 函数调用 + 结构化输出 + 长上下文 + PDF处理 |
| 合规得分 | 协议规范 + Token计费 + 计费完整性审计 |

### 测评评分

- **每题评分**：关键词匹配 / 选项匹配 / 精确匹配 / 代码结构检查 / 长度检查
- **维度得分**：各维度加权平均（0-100分）
- **综合判定**：优秀 (≥85) / 良好 (70-84) / 一般 (50-69) / 较差 (<50)

---

## 🛠 技术栈

- **后端**：Python 3.10+ / Flask / Werkzeug
- **前端**：原生 JavaScript / SSE 实时推送 / CSS3
- **协议**：OpenAI Chat Completions / Anthropic Messages API / Gemini GenerateContent
- **依赖**：`requests`, `jinja2`, `flask`, `tiktoken`

---

## 📝 版本历史

| 版本 | 日期 | 主要变更 |
|------|------|---------|
| v5.1 | 2026-08 | Cosmic Galaxy 前端重构、独立测评页面、触摸优化 |
| v2.8 | 2026-07 | Consistency v2.7 多维度加权、Identity v2.7 语义理解 |
| v2.7 | 2026-07 | 模型能力测评集成（100题，5维度）、Tab Bug 修复 |
| v2.6 | 2026-07 | 模型能力测评模块集成 |
| v2.4 | 2026-07 | 协议自动识别增强、URL路径自动发现 |
| v2.2 | 2026-07 | 计费完整性审计、Token精确计数 |
| v2.1 | 2026-07 | 思维签名验证、身份认知检测 |

---

## 🧪 测试

```bash
# 运行全部测试
pytest

# 运行特定模块测试
pytest tests/test_core/
pytest tests/test_openai/
pytest tests/test_anthropic/
pytest tests/test_gemini/
```

---

## 📄 许可证

本项目采用 [Apache License 2.0](LICENSE) 开源协议。

---

## 🙏 致谢

本项目融合了以下开源项目的优秀理念：
- **[veridrop](https://github.com/)**：模型探测、多URL回退、双Auth头策略
- **[relayAPI](https://github.com/)**：多Provider预设、API Key遮罩

---

## ⚠️ 免责声明

本工具仅用于技术检测和学术研究目的。请确保在使用前已获得相关 API 服务商的授权。使用者需自行承担因使用本工具产生的一切法律责任。
