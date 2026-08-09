"""
已知模型签名库 - 用于比对响应中的模型标识

V1: 覆盖主流模型系列
V2: 扩展到更多模型的细粒度特征
"""

# 真实 OpenAI 模型（截至 2026-05）
REAL_OPENAI_MODELS = {
    # GPT-5 系列
    "gpt-5", "gpt-5-0327", "gpt-5-mini", "gpt-5-nano",
    # GPT-4o 系列
    "gpt-4o", "gpt-4o-2024-11-20", "gpt-4o-2024-08-06",
    "gpt-4o-mini", "gpt-4o-mini-2024-07-18",
    # GPT-4.1 系列
    "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano",
    # o 系列
    "o3", "o3-2025-04-16", "o3-mini", "o3-mini-2025-01-31",
    "o4-mini", "o4-mini-2025-04-16",
    # GPT-4
    "gpt-4", "gpt-4-turbo", "gpt-4-turbo-2024-04-09",
    "gpt-4-0125-preview", "gpt-4-1106-preview",
    # 旧版
    "gpt-3.5-turbo", "gpt-3.5-turbo-0125",
}

# 真实 Anthropic 模型
REAL_ANTHROPIC_MODELS = {
    "claude-opus-4-5", "claude-opus-4-5-20250514",
    "claude-opus-4", "claude-opus-4-20250514",
    "claude-sonnet-4-5", "claude-sonnet-4-5-20250514",
    "claude-sonnet-4", "claude-sonnet-4-20250514",
    "claude-3-5-sonnet-20241022", "claude-3-5-sonnet-latest",
    "claude-3-5-haiku-20241022", "claude-3-5-haiku-latest",
    "claude-3-opus-20240229", "claude-3-sonnet-20240229",
    "claude-3-haiku-20240307",
}

# 真实 Google 模型
REAL_GOOGLE_MODELS = {
    "gemini-2.5-pro", "gemini-2.5-pro-preview-06-05",
    "gemini-2.5-flash", "gemini-2.5-flash-preview-05-20",
    "gemini-2.0-flash", "gemini-2.0-flash-001",
    "gemini-2.0-flash-lite", "gemini-2.0-flash-lite-001",
    "gemini-1.5-pro", "gemini-1.5-pro-002",
    "gemini-1.5-flash", "gemini-1.5-flash-002",
}

# 中转站常用虚假模型名（这些不是任何真实模型）
FAKE_MODEL_PATTERNS = [
    "gpt-oss", "gpt-open", "gpt-community", "gpt-shared",
    "claude-proxy", "claude-forward", "claude-relay",
    "gemini-proxy", "gemini-forward",
    "deepgpt", "open-gpt", "free-gpt",
    # 一些中转站的命名模式
    "-turbo-v2", "-fast", "-premium", "-pro-max",
]

# 已知开源模型（中转站常用的"冒充者"）
KNOWN_OPEN_SOURCE_MODELS = {
    "llama-3", "llama-3.1", "llama-3.2", "llama-4",
    "qwen-2.5", "qwen-3", "qwen-max",
    "deepseek-v3", "deepseek-v4", "deepseek-r1",
    "mixtral", "mistral-large", "mistral-medium",
    "yi-large", "command-r-plus",
}

# 知识截止日期特征（不同模型的已知事件）
KNOWLEDGE_CUTOFFS = {
    "gpt-4o": {"us_election_2024": True, "olympics_2024": True},
    "gpt-4-turbo": {"us_election_2024": False, "olympics_2024": False},
    "claude-opus-4-5": {"us_election_2024": True, "olympics_2024": True},
    "claude-3-5-sonnet": {"us_election_2024": True, "olympics_2024": True},
    "gemini-2.0-flash": {"us_election_2024": True, "olympics_2024": True},
}

# 响应头中可能泄露真实提供商的字段
PROVIDER_HEADER_PATTERNS = {
    "openai": ["openai", "oai-"],
    "anthropic": ["anthropic", "claude"],
    "google": ["google", "gcp", "vertex"],
    "azure": ["azure", "ms-"],
    "nvidia": ["nvcf", "nv-"],
    "alibaba": ["dashscope", "aliyun", "qwen"],
    "deepseek": ["deepseek"],
}

# === V2 扩展 ===

# Anthropic 消息 ID 前缀规范
ANTHROPIC_ID_PREFIXES = {
    "message": "msg_",           # 消息 ID
    "tool_use": "toolu_",        # 工具调用 ID
    "server_tool_use": "srvtoolu_",  # 服务端工具调用 ID
    "thinking": "thinking_",     # 思维块 ID（如有）
}

# 中转站特征响应头（用于检测代理商/中转站转发）
PROXY_HEADER_MARKERS = [
    "x-oneapi-request-id",
    "x-oneapi",
    "x-new-api",
    "x-forwarded-for",
    "x-real-ip",
    "x-served-by",
    "cf-ray",
    "x-vercel",
    "x-ratelimit",
    "x-proxy",
    "x-gateway",
]

# Claude 行为指纹特征
CLAUDE_BEHAVIORAL_FINGERPRINTS = {
    "phrases": [
        "i'd be happy to", "here are", "here's",
        "certainly", "let me", "of course",
    ],
    "formatting": {
        "uses_markdown_bold": True,       # 倾向使用 **bold**
        "uses_numbered_lists": True,      # 倾向使用编号列表
        "moderate_length": True,          # 中等长度结构化回答
    },
    "avoid_phrases": [
        "作为一个ai", "作为ai助手", "我是由",
        "sure thing", "absolutely!", "no problem!",
    ],
}

# GPT 行为指纹特征
GPT_BEHAVIORAL_FINGERPRINTS = {
    "phrases": [
        "certainly!", "of course!", "sure!",
        "i'd be happy to help",
    ],
    "formatting": {
        "uses_markdown_bold": True,
        "uses_bullet_points": True,
    },
}

# Gemini 行为指纹特征
GEMINI_BEHAVIORAL_FINGERPRINTS = {
    "phrases": [
        "here's", "here are", "certainly",
    ],
    "formatting": {
        "uses_markdown_bold": True,
        "uses_bullet_points": True,
    },
}

# 精确知识截止日期（用于 knowledge 检测器）
KNOWLEDGE_CUTOFF_DATES = {
    # OpenAI
    "gpt-4o": "2023-10",
    "gpt-4o-mini": "2023-10",
    "gpt-4.1": "2024-06",
    "gpt-5": "2024-06",
    "o3": "2023-10",
    "o4-mini": "2023-10",
    # Anthropic
    "claude-opus-4-5": "2025-01",
    "claude-opus-4": "2024-03",
    "claude-sonnet-4-5": "2025-01",
    "claude-sonnet-4": "2024-03",
    "claude-3-5-sonnet": "2024-04",
    "claude-3-5-haiku": "2024-07",
    # Google
    "gemini-2.5-pro": "2025-01",
    "gemini-2.5-flash": "2025-01",
    "gemini-2.0-flash": "2024-08",
    "gemini-1.5-pro": "2024-01",
    "gemini-1.5-flash": "2024-01",
}

# 官方定价（USD per 1M tokens，用于价格对比）
OFFICIAL_PRICING = {
    # OpenAI (input / output per 1M tokens)
    "gpt-5": {"input": 1.25, "output": 10.0},
    "gpt-5-mini": {"input": 0.25, "output": 2.0},
    "gpt-4o": {"input": 2.5, "output": 10.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.6},
    "gpt-4.1": {"input": 2.0, "output": 8.0},
    "gpt-4.1-mini": {"input": 0.4, "output": 1.6},
    "o3": {"input": 2.0, "output": 8.0},
    "o4-mini": {"input": 1.1, "output": 4.4},
    # Anthropic
    "claude-opus-4-5": {"input": 5.0, "output": 25.0},
    "claude-opus-4": {"input": 15.0, "output": 75.0},
    "claude-sonnet-4-5": {"input": 3.0, "output": 15.0},
    "claude-sonnet-4": {"input": 3.0, "output": 15.0},
    "claude-3-5-sonnet": {"input": 3.0, "output": 15.0},
    "claude-3-5-haiku": {"input": 0.8, "output": 4.0},
    # Google
    "gemini-2.5-pro": {"input": 1.25, "output": 10.0},
    "gemini-2.5-flash": {"input": 0.15, "output": 0.6},
    "gemini-2.0-flash": {"input": 0.1, "output": 0.4},
    "gemini-1.5-pro": {"input": 1.25, "output": 5.0},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.3},
}
