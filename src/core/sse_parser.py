"""
SSE 流式响应解析器

解析 Server-Sent Events 格式的流式响应，支持：
- data: 行解析
- content chunk 拼接
- usage/model 字段提取
- [DONE] 终止标记
- 错误事件处理
"""

from dataclasses import dataclass, field
from typing import Optional, Generator
import json


@dataclass
class SSEEvent:
    """单个 SSE 事件"""
    event: str = "message"
    data: str = ""


@dataclass
class StreamResponse:
    """流式响应的解析结果"""
    success: bool
    content: str = ""
    model: Optional[str] = None
    usage: Optional[dict] = None
    events: list[SSEEvent] = field(default_factory=list)
    chunks: list[dict] = field(default_factory=list)   # 原始 data dict 列表
    error: Optional[str] = None
    has_done: bool = False


def parse_sse_stream(
    response_iter: Generator[bytes, None, None],
) -> StreamResponse:
    """
    解析 SSE 流

    Args:
        response_iter: requests response.iter_lines() 的迭代器

    Returns:
        StreamResponse: 拼接后的完整响应
    """
    result = StreamResponse(success=True)
    content_parts: list[str] = []
    current_event = "message"
    buffer: list[str] = []

    try:
        for line in response_iter:
            if line is None:
                continue

            # requests.iter_lines() 返回 bytes 或 str
            if isinstance(line, bytes):
                line = line.decode("utf-8", errors="replace")

            line = line.rstrip("\r\n")

            # 空行 = 事件边界
            if line == "":
                if buffer:
                    data_str = "\n".join(buffer)
                    event = SSEEvent(event=current_event, data=data_str)
                    result.events.append(event)
                    _process_event(event, result, content_parts)
                    buffer = []
                    current_event = "message"
                continue

            # 注释行
            if line.startswith(":"):
                continue

            # event: 行
            if line.startswith("event:"):
                current_event = line[6:].strip()
                continue

            # data: 行（BUG-2 修复：移除过宽的 "data" 匹配，防止误匹配 database 等行）
            if line.startswith("data:"):
                data = line[5:].strip()
                buffer.append(data)
                continue

        # 处理缓冲区中剩余内容
        if buffer:
            data_str = "\n".join(buffer)
            event = SSEEvent(event=current_event, data=data_str)
            result.events.append(event)
            _process_event(event, result, content_parts)

    except Exception as e:
        result.success = False
        result.error = f"SSE 解析错误: {e}"

    result.content = "".join(content_parts)
    return result


def _process_event(event: SSEEvent, result: StreamResponse, content_parts: list[str]):
    """处理单个 SSE 事件"""
    data = event.data.strip()

    # [DONE] 标记
    if data == "[DONE]":
        result.has_done = True
        return

    # 尝试解析 JSON
    try:
        chunk = json.loads(data)
    except (json.JSONDecodeError, ValueError):
        return

    result.chunks.append(chunk)

    # 错误事件
    if "error" in chunk:
        result.success = False
        err = chunk["error"]
        result.error = err.get("message", str(err)) if isinstance(err, dict) else str(err)
        return

    # 提取 model
    if "model" in chunk and not result.model:
        result.model = chunk["model"]

    # 提取 usage（通常在最后一个 chunk）
    if "usage" in chunk and chunk["usage"]:
        result.usage = chunk["usage"]

    # OpenAI 格式 content 拼接
    choices = chunk.get("choices", [])
    if choices:
        delta = choices[0].get("delta", {})
        if "content" in delta and delta["content"]:
            content_parts.append(delta["content"])

    # Anthropic 格式 content 拼接
    if event.event == "content_block_delta":
        delta = chunk.get("delta", {})
        if delta.get("type") == "text_delta":
            text = delta.get("text", "")
            if text:
                content_parts.append(text)

    # Gemini 格式
    candidates = chunk.get("candidates", [])
    if candidates:
        parts = candidates[0].get("content", {}).get("parts", [])
        for part in parts:
            if "text" in part:
                content_parts.append(part["text"])
