"""
Anthropic 协议客户端

v2.4 修复：
  - 处理 200 状态码但非 JSON 响应（中转站返回 HTML 时给出明确错误）
  - URL 自动发现：如果 /messages 返回非 JSON，自动尝试 /v1/messages

支持：
  - Messages API（非流式）
  - Messages API（流式 SSE）
  - Extended thinking（获取 thinking_signature）
  - Tool use
  - PDF 输入
"""

import json
import requests
from typing import Optional
from ..base_client import BaseProtocolClient, ProtocolResponse, TokenUsage
from src.core.http_utils import request_with_retry
from src.core.sse_parser import parse_sse_stream


class AnthropicClient(BaseProtocolClient):
    """Anthropic Messages API 客户端"""

    def __init__(self, base_url: str, api_key: str, model: str):
        super().__init__(base_url, api_key, model)
        self.set_default_headers({
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        })
        # v2.4: URL 自动发现缓存
        self._resolved_messages_url: Optional[str] = None

    def _get_messages_url(self) -> str:
        """获取 Messages API URL，支持自动发现"""
        if self._resolved_messages_url:
            return self._resolved_messages_url
        return f"{self.base_url}/messages"

    def _try_resolve_url(self, payload: dict, detector_name: str) -> Optional[dict]:
        """v2.5: 尝试发现可用的 Messages API URL

        依次尝试多种 URL 模式：
        - {base}/messages
        - {base}/v1/messages
        - {base}/anthropic/messages
        返回第一个返回有效 JSON 的 URL 对应的响应数据。
        """
        import requests as req

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        base = self.base_url.rstrip("/")
        
        # 构建候选 URL 列表 - 扩大尝试范围
        if base.endswith("/v1"):
            url_candidates = [
                f"{base}/messages",
                f"{base.rstrip('/v1')}/v1/messages",
                f"{base.rstrip('/v1')}/messages",
            ]
        else:
            url_candidates = [
                f"{base}/messages",
                f"{base}/v1/messages",
                f"{base}/anthropic/messages",
            ]

        for url in url_candidates:
            try:
                print(f"[DEBUG] _try_resolve_url: trying {url}")
                resp = req.post(url, json=payload, headers=headers, timeout=15)
                print(f"[DEBUG] _try_resolve_url: {url} -> status={resp.status_code}")
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        if isinstance(data, dict):
                            # 有效 JSON 响应，缓存这个 URL
                            self._resolved_messages_url = url
                            return data
                    except (json.JSONDecodeError, ValueError):
                        continue
            except Exception:
                continue

        return None

    def messages(
        self,
        messages: list,
        max_tokens: int = 100,
        temperature: float = 0.1,
        system: Optional[str] = None,
        tools: Optional[list] = None,
        tool_choice: Optional[dict] = None,
        thinking: Optional[dict] = None,
        detector_name: str = "",
    ) -> ProtocolResponse:
        """发送 Messages API 请求（非流式）"""
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        # Anthropic API 规定：启用 extended thinking 时 temperature 必须为 1
        if thinking:
            payload["temperature"] = 1
        else:
            payload["temperature"] = temperature
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = tools
        if tool_choice:
            payload["tool_choice"] = tool_choice
        if thinking:
            payload["thinking"] = thinking

        url = self._get_messages_url()
        
        # DEBUG: 打印请求信息
        print(f"[DEBUG] AnthropicClient.messages: base_url={self.base_url}, url={url}, model={self.model}")

        try:
            resp = request_with_retry(
                self.session, "POST",
                url,
                json=payload,
                detector_name=detector_name,
            )
            
            # DEBUG: 打印响应状态
            print(f"[DEBUG] AnthropicClient.messages: status={resp.status_code}, headers={dict(resp.headers)}")

            if resp.status_code == 200:
                # v2.4: 安全地解析 JSON，处理非 JSON 200 响应
                try:
                    data = resp.json()
                except (json.JSONDecodeError, ValueError):
                    # 响应不是 JSON — 可能是中转站返回了 HTML
                    # 如果当前 URL 不含 /v1，尝试 /v1/messages
                    if not self._resolved_messages_url and not self.base_url.endswith("/v1"):
                        resolved_data = self._try_resolve_url(payload, detector_name)
                        if resolved_data is not None:
                            data = resolved_data
                        else:
                            return self._build_error_response(
                                f"响应不是有效 JSON（可能 URL 路径错误，已尝试 /messages 和 /v1/messages）"
                            )
                    else:
                        return self._build_error_response(
                            f"响应不是有效 JSON: {resp.text[:200]}"
                        )

                usage_data = data.get("usage", {})
                usage = TokenUsage(
                    prompt_tokens=usage_data.get("input_tokens", 0),
                    completion_tokens=usage_data.get("output_tokens", 0),
                    total_tokens=(usage_data.get("input_tokens", 0)
                                  + usage_data.get("output_tokens", 0)
                                  + usage_data.get("cache_creation_input_tokens", 0)
                                  + usage_data.get("cache_read_input_tokens", 0)),
                    cache_creation_input_tokens=usage_data.get("cache_creation_input_tokens", 0),
                    cache_read_input_tokens=usage_data.get("cache_read_input_tokens", 0),
                )
                self._record_usage(usage)

                # 解析 content blocks
                content_parts = []
                thinking_text = None
                thinking_sig = None
                for block in data.get("content", []):
                    if block.get("type") == "text":
                        content_parts.append(block.get("text", ""))
                    elif block.get("type") == "thinking":
                        thinking_text = block.get("thinking", "")
                        thinking_sig = block.get("signature")
                    elif block.get("type") == "tool_use":
                        content_parts.append(json.dumps(block))

                return ProtocolResponse(
                    success=True,
                    content="".join(content_parts) if content_parts else None,
                    model=data.get("model"),
                    headers=dict(resp.headers),
                    usage=usage,
                    status_code=resp.status_code,
                    raw_response=data,
                    thinking=thinking_text,
                    thinking_signature=thinking_sig,
                    message_id=data.get("id"),
                )
            elif resp.status_code in (403, 404) and not self._resolved_messages_url:
                # v2.5: 403/404 错误时尝试其他 URL 路径
                print(f"[DEBUG] AnthropicClient.messages: {resp.status_code} error, trying alternative URLs...")
                resolved_data = self._try_resolve_url(payload, detector_name)
                print(f"[DEBUG] AnthropicClient.messages: _try_resolve_url returned {resolved_data is not None}")
                if resolved_data is not None:
                    data = resolved_data
                    usage_data = data.get("usage", {})
                    usage = TokenUsage(
                        prompt_tokens=usage_data.get("input_tokens", 0),
                        completion_tokens=usage_data.get("output_tokens", 0),
                        total_tokens=(usage_data.get("input_tokens", 0)
                                      + usage_data.get("output_tokens", 0)
                                      + usage_data.get("cache_creation_input_tokens", 0)
                                      + usage_data.get("cache_read_input_tokens", 0)),
                        cache_creation_input_tokens=usage_data.get("cache_creation_input_tokens", 0),
                        cache_read_input_tokens=usage_data.get("cache_read_input_tokens", 0),
                    )
                    self._record_usage(usage)

                    # 解析 content blocks
                    content_parts = []
                    thinking_text = None
                    thinking_sig = None
                    for block in data.get("content", []):
                        if block.get("type") == "text":
                            content_parts.append(block.get("text", ""))
                        elif block.get("type") == "thinking":
                            thinking_text = block.get("thinking", "")
                            thinking_sig = block.get("signature")
                        elif block.get("type") == "tool_use":
                            content_parts.append(json.dumps(block))

                    return ProtocolResponse(
                        success=True,
                        content="".join(content_parts) if content_parts else None,
                        model=data.get("model"),
                        headers=dict(resp.headers),
                        usage=usage,
                        status_code=200,
                        raw_response=data,
                        thinking=thinking_text,
                        thinking_signature=thinking_sig,
                        message_id=data.get("id"),
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

    def messages_stream(
        self,
        messages: list,
        max_tokens: int = 100,
        temperature: float = 0.1,
        system: Optional[str] = None,
        tools: Optional[list] = None,
        tool_choice: Optional[dict] = None,
        thinking: Optional[dict] = None,
        detector_name: str = "",
    ) -> ProtocolResponse:
        """发送流式 Messages API 请求"""
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
            "stream": True,
        }
        # Anthropic API 规定：启用 extended thinking 时 temperature 必须为 1
        if thinking:
            payload["temperature"] = 1
        else:
            payload["temperature"] = temperature
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = tools
        if tool_choice:
            payload["tool_choice"] = tool_choice
        if thinking:
            payload["thinking"] = thinking

        url = self._get_messages_url()

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
                    prompt_tokens=stream_result.usage.get("input_tokens", 0),
                    completion_tokens=stream_result.usage.get("output_tokens", 0),
                    total_tokens=(stream_result.usage.get("input_tokens", 0)
                                  + stream_result.usage.get("output_tokens", 0)
                                  + stream_result.usage.get("cache_creation_input_tokens", 0)
                                  + stream_result.usage.get("cache_read_input_tokens", 0)),
                    cache_creation_input_tokens=stream_result.usage.get("cache_creation_input_tokens", 0),
                    cache_read_input_tokens=stream_result.usage.get("cache_read_input_tokens", 0),
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
