"""
HTTP 健壮性工具 - 指数退避重试 + 分检测器超时 + 429 限流退避

解决优化点 B（重试+超时）和 C（限流感知）。
"""

import time
import requests
from typing import Optional, Callable, Set
from dataclasses import dataclass, field


@dataclass
class RetryConfig:
    """重试配置"""
    max_retries: int = 3
    base_delay: float = 1.0       # 基础延迟秒数
    max_delay: float = 10.0       # 最大延迟
    retry_on_status: set = field(default_factory=lambda: {429, 500, 502, 503, 504})


# 分检测器超时配置（秒）- findcg.com 响应较慢，适当增加超时
DETECTOR_TIMEOUTS = {
    "basic_request": 60,
    "model_consistency": 60,
    "model_info": 60,
    "identity": 60,
    "knowledge": 60,
    "consistency": 90,
    "behavioral_signature": 90,
    "thinking_signature": 90,
    "protocol": 60,
    "integrity": 90,
    "message_id": 60,
    "token_usage": 60,
    "token_billing": 60,
    "function_calling": 90,
    "structured_output": 90,
    "pdf": 120,
    "long_context": 300,
}

DEFAULT_TIMEOUT = 90


def get_timeout(detector_name: str) -> int:
    """获取检测器专属超时"""
    return DETECTOR_TIMEOUTS.get(detector_name, DEFAULT_TIMEOUT)


def request_with_retry(
    session: requests.Session,
    method: str,
    url: str,
    detector_name: str = "",
    config: Optional[RetryConfig] = None,
    **kwargs,
) -> requests.Response:
    """
    带重试的 HTTP 请求

    - 指数退避：base_delay * 2^attempt，上限 max_delay
    - 429 限流：优先读取 Retry-After 头，否则指数退避
    - 5xx 错误：指数退避重试
    - 超时使用分检测器配置
    """
    cfg = config or RetryConfig()
    timeout = get_timeout(detector_name)
    kwargs.setdefault("timeout", timeout)

    last_exc: Optional[Exception] = None

    for attempt in range(cfg.max_retries + 1):
        try:
            resp = session.request(method, url, **kwargs)

            # 检查是否需要重试
            if resp.status_code in cfg.retry_on_status and attempt < cfg.max_retries:
                delay = _calc_delay(resp, attempt, cfg)
                time.sleep(delay)
                continue

            return resp

        except requests.exceptions.Timeout as e:
            last_exc = e
            if attempt < cfg.max_retries:
                delay = _calc_delay(None, attempt, cfg)
                time.sleep(delay)
                continue
            raise

        except requests.exceptions.ConnectionError as e:
            last_exc = e
            if attempt < cfg.max_retries:
                delay = _calc_delay(None, attempt, cfg)
                time.sleep(delay)
                continue
            raise

    # 不应到达此处，但以防万一
    if last_exc:
        raise last_exc
    raise RuntimeError("重试耗尽")


def _calc_delay(
    resp: Optional[requests.Response],
    attempt: int,
    cfg: RetryConfig,
) -> float:
    """计算退避延迟"""
    # 429 优先使用 Retry-After
    if resp is not None and resp.status_code == 429:
        retry_after = resp.headers.get("Retry-After")
        if retry_after:
            try:
                return min(float(retry_after), cfg.max_delay)
            except ValueError:
                pass

    # 指数退避
    delay = cfg.base_delay * (2 ** attempt)
    return min(delay, cfg.max_delay)
