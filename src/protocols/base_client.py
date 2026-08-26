"""
协议客户端基类

Bug 1 修复：线程安全 - 用 threading.Lock 保护 token/request 计数
BUG-7 修复：费用估算按模型查询官方定价
"""

import threading
import requests
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TokenUsage:
    """单次请求 token 消耗（v2.2 新增 cache 字段）"""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    # 缓存计费字段（v2.2 新增，Anthropic API）
    cache_creation_input_tokens: int = 0      # 创建缓存消耗的 input tokens
    cache_read_input_tokens: int = 0          # 读取缓存消耗的 input tokens（打折计费）

    @property
    def cost_usd(self) -> float:
        """粗略估算费用（按 GPT-4o 定价）"""
        return (self.prompt_tokens * 2.5 + self.completion_tokens * 10) / 1_000_000


@dataclass
class ProtocolResponse:
    """标准化协议响应"""
    success: bool
    content: Optional[str] = None
    model: Optional[str] = None
    headers: dict = field(default_factory=dict)
    usage: Optional[TokenUsage] = None
    status_code: int = 0
    raw_response: Optional[dict] = None
    error: Optional[str] = None
    # Anthropic 特有
    thinking: Optional[str] = None
    thinking_signature: Optional[str] = None
    message_id: Optional[str] = None
    # 流式
    stream_events: Optional[list] = None


class BaseProtocolClient:
    """协议客户端基类 - 线程安全"""

    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self._session_headers = {}
        self._local = threading.local()
        self._lock = threading.Lock()
        self._total_tokens = 0
        self._total_requests = 0

    @property
    def session(self) -> requests.Session:
        """获取当前线程专属 Session，避免多检测器并发共享连接状态。"""
        session = getattr(self._local, "session", None)
        if session is None:
            session = requests.Session()
            session.headers.update(self._session_headers)
            # 浏览器 UA：绕过 Cloudflare WAF 对非浏览器 UA 的 403 拦截
            from src.core.http_utils import BROWSER_HEADERS
            session.headers.update(BROWSER_HEADERS)
            self._local.session = session
        return session

    def set_default_headers(self, headers: dict) -> None:
        """设置所有线程新建 Session 都会继承的默认请求头。"""
        self._session_headers.update(headers)
        self.session.headers.update(headers)

    def close(self) -> None:
        """关闭当前线程持有的 Session。"""
        session = getattr(self._local, "session", None)
        if session is not None:
            session.close()
            self._local.session = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _record_usage(self, usage: Optional[TokenUsage]):

        """记录 token 消耗（线程安全）"""
        with self._lock:
            self._total_requests += 1
            if usage:
                self._total_tokens += usage.total_tokens

    def get_cost_summary(self) -> dict:
        """获取消耗摘要（线程安全）—— 按模型官方定价估算"""
        with self._lock:
            tokens = self._total_tokens
            requests_count = self._total_requests
        try:
            from src.utils.price_db import get_official_price
            price = get_official_price(self.model)
            input_price = price.get("input") or 2.5
            output_price = price.get("output") or 10.0
            # 粗略按 60% input / 40% output 估算
            estimated = tokens * (input_price * 0.6 + output_price * 0.4) / 1_000_000
        except Exception:
            estimated = tokens * 2.5 / 1_000_000
        return {
            "total_tokens": tokens,
            "total_requests": requests_count,
            "estimated_cost_usd": estimated,
        }

    def _build_error_response(self, error: str, status_code: int = 0) -> ProtocolResponse:
        """构建错误响应"""
        return ProtocolResponse(
            success=False,
            error=error,
            status_code=status_code,
        )
