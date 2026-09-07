"""
协议客户端基类

Bug 1 修复：线程安全 - 用 threading.Lock 保护 token/request 计数
BUG-7 修复：费用估算按模型查询官方定价
v3.0.3：预算口径改为"请求信封"——按我方实际发出的请求内容估算 token，
完全不依赖中转站上报的数字。背景：连续实测发现两类中转站分别以
cache_read（Kiro 类）和普通 input/cache_creation（beiluoxi 类）上报
数万/请求的自身系统提示开销，任何基于上报数字的预算都会被对方单方面
打爆（反欺诈工具的检测深度不能由被检测方控制）。上报数字仅保留两个
用途：展示对账（total_tokens）与费用兜底估算（get_billable_cost_usd）。
"""

import json
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
    # v3.0.1 新增（OpenAI 格式）
    cached_tokens: int = 0                    # usage.prompt_tokens_details.cached_tokens
    # v3.0.3: 全价输入当量——按该协议真实计费折扣折算后的输入 token 数
    # （Anthropic: input + 1.25×cache_creation + 0.1×cache_read；
    #   OpenAI: prompt - 0.5×cached；Gemini: prompt）。0=未设置。
    # 用于费用兜底估算，不再参与检测预算。
    cost_input_equiv: float = 0.0


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
        self._total_tokens = 0          # 展示口径：中转站上报的总量
        self._envelope_tokens = 0       # v3.0.3 预算口径：我方请求信封估算
        self._input_equiv_total = 0.0   # v3.0.3 费用口径：全价输入当量累计
        self._output_total = 0          # v3.0.3 费用口径：输出 token 累计
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

        """记录 token 消耗（线程安全）。上报数字仅入展示/费用口径，不入预算。"""
        with self._lock:
            self._total_requests += 1
            if usage:
                self._total_tokens += usage.total_tokens
                self._output_total += usage.completion_tokens
                if usage.cost_input_equiv > 0:
                    self._input_equiv_total += usage.cost_input_equiv
                else:
                    self._input_equiv_total += usage.prompt_tokens

    def _add_envelope(self, payload) -> int:
        """v3.0.3: 按我方实际发出的请求 payload 估算 token 并计入预算口径。

        估算 = count_tokens(json(payload))（已含 messages/tools/max_tokens）。
        这是检测预算的唯一记账来源——中转站上报的数字不参与预算，
        防止被检测方通过虚报用量单方面关停检测深度。
        """
        try:
            from src.utils.token_counter import count_tokens
            est = count_tokens(json.dumps(payload, ensure_ascii=False, default=str))
        except Exception:
            try:
                est = len(json.dumps(payload, ensure_ascii=False, default=str)) // 4
            except Exception:
                est = 200
        with self._lock:
            self._envelope_tokens += max(est, 1)
        return est

    def get_budget_tokens(self) -> int:
        """获取预算口径的累计消耗（线程安全，供 Runner 预算扣减使用）

        v3.0.3: 语义改为"请求信封"——我方实际发出的请求内容估算，
        与中转站上报无关。
        """
        with self._lock:
            return self._envelope_tokens

    def get_billable_cost_usd(self) -> float:
        """v3.0.3: 按中转站上报口径 + 官方价折算的预估费用（钱包兜底用）。

        输入按协议真实折扣折算（缓存读取/命中打折、缓存写入 1.25x），
        输出按全价。这是"如果它如实上报且按官方价计费，你大概花多少"。
        """
        with self._lock:
            input_equiv = self._input_equiv_total
            output = self._output_total
        try:
            from src.utils.price_db import get_official_price
            price = get_official_price(self.model)
            input_price = price.get("input") or 2.5
            output_price = price.get("output") or 10.0
        except Exception:
            input_price, output_price = 2.5, 10.0
        return (input_equiv * input_price + output * output_price) / 1_000_000

    def get_cost_summary(self) -> dict:
        """获取消耗摘要（线程安全）

        - total_tokens: 中转站上报总量（对账口径）
        - budget_tokens: 请求信封口径（检测预算）
        - estimated_cost_usd: 按上报口径+官方价折扣折算的预估费用
        """
        with self._lock:
            tokens = self._total_tokens
            envelope = self._envelope_tokens
            requests_count = self._total_requests
        estimated = self.get_billable_cost_usd()
        return {
            "total_tokens": tokens,
            "budget_tokens": envelope,
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
