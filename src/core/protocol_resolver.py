"""
协议自动检测 + 降级回退 + URL 路径自动发现

v2.4 修复：
  - 探活时验证响应是否为 JSON（防止中转站对任意路径返回 200 HTML）
  - 尝试多种 URL 路径（/messages 和 /v1/messages），自动发现正确端点
  - 如果 /v1/messages 可用但 /messages 不可用，自动修正 base_url

Bug 3 修复：
  - 根据模型名推断原生协议
  - 尝试原生 API 探活（最小请求）
  - 失败则降级到 OpenAI 兼容协议
  - 降级时报告标注"协议降级"并跳过协议特有检测器（如 thinking_signature）
"""

import json
from .models import Protocol
from .http_utils import BROWSER_HEADERS


# 模型名 → 原生协议映射
MODEL_PROTOCOL_MAP = {
    # Anthropic
    "claude": Protocol.ANTHROPIC,
    "claude-opus": Protocol.ANTHROPIC,
    "claude-sonnet": Protocol.ANTHROPIC,
    "claude-haiku": Protocol.ANTHROPIC,
    # Google
    "gemini": Protocol.GEMINI,
    "gemma": Protocol.GEMINI,
    # OpenAI
    "gpt": Protocol.OPENAI,
    "o3": Protocol.OPENAI,
    "o4": Protocol.OPENAI,
    "chatgpt": Protocol.OPENAI,
}


def infer_protocol(model: str) -> Protocol:
    """根据模型名推断原生协议"""
    m = model.lower()
    for prefix, proto in MODEL_PROTOCOL_MAP.items():
        if m.startswith(prefix):
            return proto
    # 默认 OpenAI 兼容
    return Protocol.OPENAI


class ProtocolResolver:
    """协议解析器 - 自动检测 + 降级回退 + URL 路径发现"""

    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.native_protocol = infer_protocol(model)
        self.resolved_protocol: Protocol = self.native_protocol
        self.degraded: bool = False
        self.degrade_reason: str = ""

    def resolve(self) -> tuple[Protocol, bool, str]:
        """
        解析协议，尝试原生 API 探活

        Returns:
            (protocol, degraded, reason)

        v2.4: 探活成功后会修正 self.base_url 为可用的 base_url
        """
        # OpenAI 协议不需要降级（它就是兼容协议）
        if self.native_protocol == Protocol.OPENAI:
            # v2.4: 对 OpenAI 也尝试发现正确的 base_url
            self._resolve_openai_base_url()
            return Protocol.OPENAI, False, ""

        # 尝试原生协议探活
        success, reason = self._probe_native()

        if success:
            return self.native_protocol, False, ""

        # 降级到 OpenAI 兼容
        self.degraded = True
        self.degrade_reason = f"原生 {self.native_protocol.value} 协议不可用: {reason}，降级到 OpenAI 兼容协议"
        self.resolved_protocol = Protocol.OPENAI
        # 降级时也尝试发现 OpenAI 兼容的 base_url
        self._resolve_openai_base_url()
        return Protocol.OPENAI, True, self.degrade_reason

    def _resolve_openai_base_url(self):
        """v2.5: 尝试发现 OpenAI 兼容的 base_url（自动补 /v1）"""
        import requests

        base = self.base_url.rstrip("/")
        # 如果已经以 /v1 结尾，不需要补
        if base.endswith("/v1"):
            return

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            **BROWSER_HEADERS,
        }

        # 尝试多种 URL 模式 - 扩大探测范围
        url_candidates = [
            (f"{base}/v1/models", f"{base}/v1"),
            (f"{base}/models", f"{base}"),
            (f"{base}/api/v1/models", f"{base}/api/v1"),
            (f"{base}/openai/v1/models", f"{base}/openai/v1"),
        ]

        for models_url, effective_base in url_candidates:
            try:
                resp = requests.get(models_url, headers=headers, timeout=8)
                if resp.status_code == 200:
                    # 验证是否为 JSON
                    try:
                        data = resp.json()
                        if isinstance(data, dict) and ("data" in data or "models" in data):
                            self.base_url = effective_base
                            return
                    except (json.JSONDecodeError, ValueError):
                        continue
            except Exception:
                continue

        # v2.5: 如果 GET /models 探测失败，尝试 POST /v1/chat/completions
        # 某些中转站可能不支持 /models 但支持 /chat/completions
        chat_payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 5,
        }
        chat_url_candidates = [
            (f"{base}/v1/chat/completions", f"{base}/v1"),
            (f"{base}/chat/completions", f"{base}"),
            (f"{base}/api/v1/chat/completions", f"{base}/api/v1"),
        ]
        for chat_url, effective_base in chat_url_candidates:
            try:
                resp = requests.post(chat_url, json=chat_payload, headers=headers, timeout=8)
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        if isinstance(data, dict) and "choices" in data:
                            self.base_url = effective_base
                            return
                    except (json.JSONDecodeError, ValueError):
                        continue
            except Exception:
                continue

    def _probe_native(self) -> tuple[bool, str]:
        """尝试原生协议探活（最小请求）"""
        try:
            if self.native_protocol == Protocol.ANTHROPIC:
                return self._probe_anthropic()
            elif self.native_protocol == Protocol.GEMINI:
                return self._probe_gemini()
        except Exception as e:
            return False, str(e)

        return False, "未知协议"

    def _probe_anthropic(self) -> tuple[bool, str]:
        """探活 Anthropic Messages API

        v2.4 修复：尝试多种 URL 路径，验证响应为 JSON
        """
        import requests

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
            **BROWSER_HEADERS,
        }
        payload = {
            "model": self.model,
            "max_tokens": 5,
            "messages": [{"role": "user", "content": "Hi"}],
        }

        # v2.4: 尝试多种 URL 路径
        # 如果 base_url 已经以 /v1 结尾，直接用 /messages
        # 否则先尝试 /messages，再尝试 /v1/messages
        if self.base_url.endswith("/v1"):
            url_candidates = [f"{self.base_url}/messages"]
        else:
            url_candidates = [
                f"{self.base_url}/messages",
                f"{self.base_url}/v1/messages",
            ]

        for url in url_candidates:
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=15)

                if resp.status_code == 200:
                    # v2.4: 验证响应是否为 JSON（防止中转站返回 200 HTML）
                    try:
                        data = resp.json()
                        if isinstance(data, dict) and ("content" in data or "id" in data or "type" in data):
                            # 探活成功，修正 base_url
                            if url.endswith("/v1/messages"):
                                self.base_url = self.base_url + "/v1"
                            return True, ""
                        else:
                            # 200 但不是 Anthropic API 响应格式
                            continue
                    except (json.JSONDecodeError, ValueError):
                        # 响应不是 JSON，继续尝试下一个 URL
                        continue
                elif resp.status_code == 404:
                    continue  # 端点不存在，尝试下一个
                elif resp.status_code == 401:
                    # 认证失败，说明端点存在但 key 错
                    return False, f"认证失败 (401)"
                else:
                    continue  # 其他错误，尝试下一个

            except requests.exceptions.Timeout:
                continue
            except requests.exceptions.ConnectionError:
                continue
            except Exception:
                continue

        return False, "所有 Anthropic 端点探活失败（/messages 和 /v1/messages 均不可用）"

    def _probe_gemini(self) -> tuple[bool, str]:
        """探活 Gemini API

        v2.4 修复：尝试多种 URL 路径，验证响应为 JSON
        """
        import requests

        payload = {
            "contents": [{"parts": [{"text": "Hi"}]}],
            "generationConfig": {"maxOutputTokens": 5},
        }

        # 尝试多种 URL 路径
        if self.base_url.endswith("/v1beta"):
            url_candidates = [f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"]
        else:
            url_candidates = [
                f"{self.base_url}/v1beta/models/{self.model}:generateContent?key={self.api_key}",
                f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}",
            ]

        for url in url_candidates:
            try:
                resp = requests.post(url, json=payload, headers=BROWSER_HEADERS, timeout=15)

                if resp.status_code == 200:
                    # v2.4: 验证响应是否为 JSON
                    try:
                        data = resp.json()
                        if isinstance(data, dict) and ("candidates" in data or "usageMetadata" in data):
                            # 探活成功，修正 base_url
                            if "/v1beta/" in url and not self.base_url.endswith("/v1beta"):
                                self.base_url = self.base_url + "/v1beta"
                            return True, ""
                        else:
                            continue
                    except (json.JSONDecodeError, ValueError):
                        continue
                elif resp.status_code == 404:
                    continue
                elif resp.status_code == 401 or resp.status_code == 403:
                    return False, f"认证失败 ({resp.status_code})"
                else:
                    continue

            except requests.exceptions.Timeout:
                continue
            except requests.exceptions.ConnectionError:
                continue
            except Exception:
                continue

        return False, "所有 Gemini 端点探活失败"
