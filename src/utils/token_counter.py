"""
共享 Token 计数工具

提供 tiktoken 精确计数（可用时）和 len//4 回退方案，
供 billing_integrity / token_billing / token_usage 等检测器统一使用。
"""

try:
    import tiktoken
    _HAS_TIKTOKEN = True

    _ENCODER = tiktoken.get_encoding("cl100k_base")

    def count_tokens(text: str) -> int:
        """用 tiktoken cl100k_base 精确计算 token 数"""
        return len(_ENCODER.encode(text))
except ImportError:
    _HAS_TIKTOKEN = False

    def count_tokens(text: str) -> int:
        """回退方案：1 token ~= 4 字符"""
        return max(1, len(text) // 4)


# OpenAI chat 格式的消息结构 token 开销（<|im_start|>user\n...<|im_end|>\n）
OPENAI_MESSAGE_OVERHEAD = 4

# Anthropic Messages API 的消息结构 token 开销
ANTHROPIC_MESSAGE_OVERHEAD = 5
