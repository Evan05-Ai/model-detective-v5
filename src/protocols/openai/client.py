"""
OpenAI 协议客户端

v2.4 修复：
  - 处理 200 状态码但非 JSON 响应（中转站返回 HTML 时给出明确错误）
  - URL 自动发现：如果 /chat/completions 返回非 JSON，自动尝试 /v1/chat/completions

支持：
  - chat completions（非流式）
  - chat completions（流式 SSE）
  - models 列表查询
  - function calling
  - structured output (response_format)
"""

import json
import requests
from typing import Optional
from ..base_client import BaseProtocolClient, ProtocolResponse, TokenUsage
from src.core.http_utils import request_with_retry
from src.core.sse_parser import parse_sse_stream


class OpenAIClient(BaseProtocolClient):
    """OpenAI 兼容协议客户端"""

    def __init__(self, base_url: str, api_key: str, model: str):
        super().__init__(base_url, api_key, model)
        self.set_default_headers({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        })
        # v2.4: URL 自动发现缓存
        self._resolved_chat_url: Optional[str] = None

    def _get_chat_url(self) -> str:
        """获取 chat completions URL，支持自动发现"""
        if self._resolved_chat_url:
            return self._resolved_chat_url
        # v2.5: 优先尝试 /v1/chat/completions，因为大多数 API 使用这个路径
        base = self.base_url.rstrip("/")
        if base.endswith("/v1"):
            return f"{base}/chat/completions"
        else:
            # 如果 base_url 不包含 /v1，尝试添加 /v1/chat/completions
            return f"{base}/v1/chat/completions"

    def _try_resolve_chat_url(self, payload: dict, detector_name: str) -> Optional[dict]:
        """v2.5: 尝试发现可用的 chat completions URL

        依次尝试多种 URL 模式：
        - {base}/v1/chat/completions
        - {base}/chat/completions
        - {base}/api/v1/chat/completions
        返回第一个返回有效 JSON 的 URL 对应的响应数据。
        """
        base = self.base_url.rstrip("/")

        # 构建候选 URL 列表 - 扩大尝试范围
        url_candidates = []
        
        if base.endswith("/v1"):
            # 如果 base 以 /v1 结尾，尝试带和不带 /v1 的路径
            url_candidates = [
                f"{base}/chat/completions",
                f"{base.rstrip('/v1')}/v1/chat/completions",  # 避免重复 /v1
                f"{base.rstrip('/v1')}/chat/completions",
            ]
        else:
            # 如果 base 不以 /v1 结尾，尝试多种组合
            url_candidates = [
                f"{base}/v1/chat/completions",
                f"{base}/chat/completions",
                f"{base}/api/v1/chat/completions",
                f"{base}/openai/v1/chat/completions",
            ]

        last_error = None
        for url in url_candidates:
            try:
                resp = request_with_retry(
                    self.session, "POST",
                    url,
                    json=payload,
                    detector_name=detector_name,
                )
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        if isinstance(data, dict) and "choices" in data:
                            self._resolved_chat_url = url
                            return data
                    except (json.JSONDecodeError, ValueError):
                        continue
                else:
                    # 记录最后一个错误状态码
                    last_error = resp.status_code
            except Exception as e:
                continue

        return None

    def chat(
        self,
        messages: list,
        max_tokens: int = 100,
        temperature: float = 0.1,
        tools: Optional[list] = None,
        response_format: Optional[dict] = None,
        detector_name: str = "",
    ) -> ProtocolResponse:
        """发送聊天请求（非流式）"""
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools
        if response_format:
            payload["response_format"] = response_format

        url = self._get_chat_url()

        try:
            resp = request_with_retry(
                self.session, "POST",
                url,
                json=payload,
                detector_name=detector_name,
            )

            if resp.status_code == 200:
                # v2.4: 安全地解析 JSON，处理非 JSON 200 响应
                try:
                    data = resp.json()
                except (json.JSONDecodeError, ValueError):
                    # 响应不是 JSON — 可能 URL 路径错误
                    if not self._resolved_chat_url and not self.base_url.endswith("/v1"):
                        resolved_data = self._try_resolve_chat_url(payload, detector_name)
                        if resolved_data is not None:
                            data = resolved_data
                        else:
                            return self._build_error_response(
                                "响应不是有效 JSON（已尝试 /chat/completions 和 /v1/chat/completions）"
                            )
                    else:
                        return self._build_error_response(
                            f"响应不是有效 JSON: {resp.text[:200]}"
                        )

                usage_data = data.get("usage", {})
                usage = TokenUsage(
                    prompt_tokens=usage_data.get("prompt_tokens", 0),
                    completion_tokens=usage_data.get("completion_tokens", 0),
                    total_tokens=usage_data.get("total_tokens", 0),
                )
                self._record_usage(usage)

                choice = data.get("choices", [{}])[0]
                msg = choice.get("message", {})
                content = msg.get("content")
                reasoning = msg.get("reasoning") or msg.get("reasoning_content")
                if not content and reasoning:
                    content = reasoning

                return ProtocolResponse(
                    success=True,
                    content=content,
                    model=data.get("model"),
                    headers=dict(resp.headers),
                    usage=usage,
                    status_code=resp.status_code,
                    raw_response=data,
                )
            elif resp.status_code in (403, 404) and not self._resolved_chat_url:
                # v2.5: 403/404 错误时尝试其他 URL 路径
                resolved_data = self._try_resolve_chat_url(payload, detector_name)
                if resolved_data is not None:
                    data = resolved_data
                    usage_data = data.get("usage", {})
                    usage = TokenUsage(
                        prompt_tokens=usage_data.get("prompt_tokens", 0),
                        completion_tokens=usage_data.get("completion_tokens", 0),
                        total_tokens=usage_data.get("total_tokens", 0),
                    )
                    self._record_usage(usage)

                    choice = data.get("choices", [{}])[0]
                    msg = choice.get("message", {})
                    content = msg.get("content")
                    reasoning = msg.get("reasoning") or msg.get("reasoning_content")
                    if not content and reasoning:
                        content = reasoning

                    return ProtocolResponse(
                        success=True,
                        content=content,
                        model=data.get("model"),
                        headers=dict(resp.headers),
                        usage=usage,
                        status_code=200,
                        raw_response=data,
                    )
                else:
                    return self._build_error_response(
                        f"HTTP {resp.status_code}: {resp.text[:300]}",
                        resp.status_code,
                    )
            else:
                return self._build_error_response(
                    f"HTTP {resp.status_code}: {resp.text[:300]}",
                    resp.status_code,
                )

        except requests.exceptions.Timeout:
            return self._build_error_response("请求超时")
        except Exception as e:
            return self._build_error_response(str(e))

    def chat_stream(
        self,
        messages: list,
        max_tokens: int = 100,
        temperature: float = 0.1,
        detector_name: str = "",
    ) -> ProtocolResponse:
        """发送流式聊天请求"""
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }

        url = self._get_chat_url()

        try:
            resp = self.session.post(
                url,
                json=payload,
                stream=True,
                timeout=120,
            )

            if resp.status_code != 200:
                return self._build_error_response(
                    f"HTTP {resp.status_code}: {resp.text[:300]}",
                    resp.status_code,
                )

            stream_result = parse_sse_stream(resp.iter_lines())

            usage = None
            if stream_result.usage:
                usage = TokenUsage(
                    prompt_tokens=stream_result.usage.get("prompt_tokens", 0),
                    completion_tokens=stream_result.usage.get("completion_tokens", 0),
                    total_tokens=stream_result.usage.get("total_tokens", 0),
                )
            self._record_usage(usage)

            return ProtocolResponse(
                success=stream_result.success,
                content=stream_result.content,
                model=stream_result.model,
                headers=dict(resp.headers),
                usage=usage,
                status_code=resp.status_code,
                error=stream_result.error,
                stream_events=stream_result.events,
            )

        except requests.exceptions.Timeout:
            return self._build_error_response("流式请求超时")
        except Exception as e:
            return self._build_error_response(str(e))

    def list_models(self) -> tuple[bool, list, str]:
        """查询 /v1/models 端点"""
        try:
            resp = request_with_retry(
                self.session, "GET",
                f"{self.base_url}/models",
                detector_name="basic_request",
            )
            if resp.status_code == 200:
                try:
                    data = resp.json()
                except (json.JSONDecodeError, ValueError):
                    return False, [], "响应不是有效 JSON"
                models = [m.get("id", "") for m in data.get("data", [])]
                return True, models, ""
            else:
                return False, [], f"HTTP {resp.status_code}: {resp.text[:200]}"
        except Exception as e:
            return False, [], str(e)
