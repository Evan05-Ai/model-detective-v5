"""
Gemini 协议客户端

支持：
  - generateContent（非流式）
  - streamGenerateContent（流式 SSE）
  - function calling
  - structured output (responseSchema)
"""

import json
import requests
from typing import Optional
from ..base_client import BaseProtocolClient, ProtocolResponse, TokenUsage
from src.core.http_utils import request_with_retry
from src.core.sse_parser import parse_sse_stream


class GeminiClient(BaseProtocolClient):
    """Google Gemini API 客户端"""

    def __init__(self, base_url: str, api_key: str, model: str):
        super().__init__(base_url, api_key, model)
        # Gemini 通过 URL query 传递 key
        self.set_default_headers({
            "Content-Type": "application/json",
        })


    def _build_url(self, method: str = "generateContent") -> str:
        """构建 Gemini API URL"""
        return f"{self.base_url}/models/{self.model}:{method}?key={self.api_key}"

    def generate(
        self,
        contents: list,
        max_tokens: int = 100,
        temperature: float = 0.1,
        tools: Optional[list] = None,
        response_schema: Optional[dict] = None,
        detector_name: str = "",
    ) -> ProtocolResponse:
        """发送 generateContent 请求（非流式）"""
        payload = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": temperature,
            },
        }
        if tools:
            payload["tools"] = tools
        if response_schema:
            payload["generationConfig"]["responseMimeType"] = "application/json"
            payload["generationConfig"]["responseSchema"] = response_schema

        try:
            resp = request_with_retry(
                self.session, "POST",
                self._build_url("generateContent"),
                json=payload,
                detector_name=detector_name,
            )

            if resp.status_code == 200:
                data = resp.json()
                usage_data = data.get("usageMetadata", {})
                usage = TokenUsage(
                    prompt_tokens=usage_data.get("promptTokenCount", 0),
                    completion_tokens=usage_data.get("candidatesTokenCount", 0),
                    total_tokens=usage_data.get("totalTokenCount", 0),
                )
                self._record_usage(usage)

                # 提取内容
                content_parts = []
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    for part in parts:
                        if "text" in part:
                            content_parts.append(part["text"])

                return ProtocolResponse(
                    success=True,
                    content="".join(content_parts) if content_parts else None,
                    model=data.get("modelVersion", self.model),
                    headers=dict(resp.headers),
                    usage=usage,
                    status_code=resp.status_code,
                    raw_response=data,
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

    def generate_stream(
        self,
        contents: list,
        max_tokens: int = 100,
        temperature: float = 0.1,
        detector_name: str = "",
    ) -> ProtocolResponse:
        """发送流式 generateContent 请求"""
        payload = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": temperature,
            },
        }

        try:
            resp = self.session.post(
                self._build_url("streamGenerateContent"),
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
                    prompt_tokens=stream_result.usage.get("promptTokenCount", 0),
                    completion_tokens=stream_result.usage.get("candidatesTokenCount", 0),
                    total_tokens=stream_result.usage.get("totalTokenCount", 0),
                )
            self._record_usage(usage)

            return ProtocolResponse(
                success=stream_result.success,
                content=stream_result.content,
                model=stream_result.model or self.model,
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
        """查询 Gemini 模型列表"""
        try:
            resp = request_with_retry(
                self.session, "GET",
                f"{self.base_url}/models?key={self.api_key}",
                detector_name="basic_request",
            )
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("name", "").replace("models/", "") for m in data.get("models", [])]
                return True, models, ""
            else:
                return False, [], f"HTTP {resp.status_code}: {resp.text[:200]}"
        except Exception as e:
            return False, [], str(e)
