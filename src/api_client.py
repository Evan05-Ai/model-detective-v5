"""API 客户端封装 - 所有 HTTP 请求都经过这里，统一追踪 token 消耗"""

import requests
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TokenUsage:
    """单次请求的 token 消耗（v2.2 新增 cache 字段）"""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    # 缓存计费字段（v2.2 新增，Anthropic API）
    cache_creation_input_tokens: int = 0      # 创建缓存消耗的 input tokens
    cache_read_input_tokens: int = 0          # 读取缓存消耗的 input tokens（打折计费）

    @property
    def cost_usd(self) -> float:
        """粗略估算费用（按 GPT-4o 定价：$2.5/1M input, $10/1M output）"""
        return (self.prompt_tokens * 2.5 + self.completion_tokens * 10) / 1_000_000


@dataclass
class ChatResponse:
    """标准化的聊天响应"""
    success: bool
    model_field: Optional[str] = None  # 响应中的 model 字段
    content: Optional[str] = None
    reasoning: Optional[str] = None
    headers: dict = field(default_factory=dict)
    usage: Optional[TokenUsage] = None
    status_code: int = 0
    raw_response: Optional[dict] = None
    error: Optional[str] = None


class APIClient:
    """OpenAI 兼容 API 客户端"""

    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        })
        # 浏览器 UA：绕过 Cloudflare WAF 对非浏览器 UA 的 403 拦截
        from src.core.http_utils import BROWSER_HEADERS
        self.session.headers.update(BROWSER_HEADERS)
        self.total_tokens_used = 0
        self.total_requests = 0

    def chat(self, messages: list, max_tokens: int = 100,
             temperature: float = 0.1) -> ChatResponse:
        """发送聊天请求"""
        self.total_requests += 1
        try:
            resp = self.session.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": self.model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
                timeout=30
            )

            usage = None
            if resp.status_code == 200:
                data = resp.json()
                usage_data = data.get("usage", {})
                usage = TokenUsage(
                    prompt_tokens=usage_data.get("prompt_tokens", 0),
                    completion_tokens=usage_data.get("completion_tokens", 0),
                    total_tokens=usage_data.get("total_tokens", 0),
                )
                self.total_tokens_used += usage.total_tokens

                choice = data.get("choices", [{}])[0]
                msg = choice.get("message", {})

                # 推理模型可能把答案放在 reasoning_content 而非 content
                effective_content = msg.get("content")
                reasoning = msg.get("reasoning") or msg.get("reasoning_content")
                if not effective_content and reasoning:
                    effective_content = reasoning

                return ChatResponse(
                    success=True,
                    model_field=data.get("model"),
                    content=effective_content,
                    reasoning=reasoning,
                    headers=dict(resp.headers),
                    usage=usage,
                    status_code=resp.status_code,
                    raw_response=data,
                )
            else:
                return ChatResponse(
                    success=False,
                    headers=dict(resp.headers),
                    status_code=resp.status_code,
                    error=resp.text[:500],
                )

        except requests.exceptions.Timeout:
            return ChatResponse(success=False, error="请求超时 (30s)")
        except Exception as e:
            return ChatResponse(success=False, error=str(e))

    def list_models(self) -> tuple[bool, list, str]:
        """查询 /v1/models 端点，返回 (成功, 模型列表, 错误信息)"""
        try:
            resp = self.session.get(
                f"{self.base_url}/models",
                timeout=15
            )
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("id", "") for m in data.get("data", [])]
                return True, models, ""
            else:
                return False, [], f"HTTP {resp.status_code}: {resp.text[:200]}"
        except Exception as e:
            return False, [], str(e)

    def get_cost_summary(self) -> dict:
        """获取总消耗摘要"""
        return {
            "total_requests": self.total_requests,
            "total_tokens": self.total_tokens_used,
        }
