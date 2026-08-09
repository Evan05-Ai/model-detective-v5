"""
模型名称处理工具函数（v2.6 提取公共代码）

统一处理模型名称的规范化、前缀剥离等操作。
"""

import re


# 中转站常见前缀
RELAY_PREFIXES = [
    "aiproxy-",
    "proxy-",
    "relay-",
    "api-",
    "custom-",
    "forward-",
    "gateway-",
]


def strip_relay_prefix(name: str) -> str:
    """
    去掉中转站常见前缀
    
    Args:
        name: 原始模型名称
    
    Returns:
        去掉前缀后的模型名称
    
    Example:
        >>> strip_relay_prefix("aiproxy-claude-opus-4")
        "claude-opus-4"
    """
    name_lower = name.lower()
    for prefix in RELAY_PREFIXES:
        if name_lower.startswith(prefix):
            return name[len(prefix):]
    return name


def normalize_model_name(name: str) -> str:
    """
    规范化模型名称：去掉前缀 + 移除非字母数字字符
    
    用于比较两个模型名称是否实质相同（忽略格式差异）
    
    Args:
        name: 原始模型名称
    
    Returns:
        规范化后的模型名称
    
    Example:
        >>> normalize_model_name("claude-opus-4.8")
        "claudeopus48"
        >>> normalize_model_name("aiproxy-claude-opus-4-8")
        "claudeopus48"
    """
    name = strip_relay_prefix(name)
    return re.sub(r'[^a-z0-9]', '', name.lower())


def extract_version_number(name: str) -> str:
    """
    提取模型名称中的版本号
    
    Args:
        name: 模型名称
    
    Returns:
        版本号字符串，如果没有则返回空字符串
    
    Example:
        >>> extract_version_number("claude-opus-4-5-20250514")
        "4-5-20250514"
        >>> extract_version_number("gpt-4o")
        "4o"
    """
    # 匹配版本号模式（数字、点、连字符的组合）
    match = re.search(r'[\d\.-]+[\d\w]*$', name.lower())
    return match.group(0) if match else ""


def get_model_family(name: str) -> str:
    """
    获取模型家族（claude/gpt/gemini 等）
    
    Args:
        name: 模型名称
    
    Returns:
        模型家族名称，未知则返回 "unknown"
    """
    name_lower = name.lower()
    
    families = {
        "claude": ["claude"],
        "gpt": ["gpt"],
        "gemini": ["gemini"],
        "llama": ["llama"],
        "qwen": ["qwen"],
        "deepseek": ["deepseek"],
        "mistral": ["mistral", "mixtral"],
    }
    
    for family, keywords in families.items():
        if any(kw in name_lower for kw in keywords):
            return family
    
    return "unknown"


def are_models_equivalent(name1: str, name2: str) -> bool:
    """
    判断两个模型名称是否实质等价
    
    考虑：
    - 中转站前缀差异
    - 连字符和点号差异（4-8 vs 4.8）
    - 大小写差异
    
    Args:
        name1: 第一个模型名称
        name2: 第二个模型名称
    
    Returns:
        是否实质等价
    
    Example:
        >>> are_models_equivalent("claude-opus-4.8", "aiproxy-claude-opus-4-8")
        True
    """
    return normalize_model_name(name1) == normalize_model_name(name2)


def are_models_similar(name1: str, name2: str) -> bool:
    """
    判断两个模型名称是否相似（可能是同一系列的不同版本）
    
    Args:
        name1: 第一个模型名称
        name2: 第二个模型名称
    
    Returns:
        是否相似
    """
    norm1 = normalize_model_name(name1)
    norm2 = normalize_model_name(name2)
    
    # 完全等价
    if norm1 == norm2:
        return True
    
    # 互相包含
    if norm1 in norm2 or norm2 in norm1:
        return True
    
    # 同一家族
    family1 = get_model_family(name1)
    family2 = get_model_family(name2)
    if family1 == family2 and family1 != "unknown":
        return True
    
    return False
