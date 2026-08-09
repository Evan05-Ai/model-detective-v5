#!/usr/bin/env python3
"""SSE 解析器测试"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.core.sse_parser import parse_sse_stream, StreamResponse, SSEEvent


def _make_iterator(lines):
    """模拟 requests.iter_lines()"""
    for line in lines:
        yield line.encode("utf-8")


def test_empty_stream():
    result = parse_sse_stream(_make_iterator([]))
    assert result.success
    assert result.content == ""
    assert not result.has_done
    print("  [OK] test_empty_stream")


def test_simple_openai_stream():
    lines = [
        'data: {"id":"123","object":"chat.completion.chunk","choices":[{"delta":{"content":"Hello"}}]}',
        '',
        'data: {"id":"123","choices":[{"delta":{"content":" world"}}]}',
        '',
        'data: [DONE]',
        '',
    ]
    result = parse_sse_stream(_make_iterator(lines))
    assert result.success
    assert "Hello" in result.content
    assert "world" in result.content
    assert result.has_done
    assert result.chunks[0]["id"] == "123"
    print("  [OK] test_simple_openai_stream")


def test_openai_stream_with_usage():
    lines = [
        'data: {"id":"123","choices":[{"delta":{"content":"Hello"}}]}',
        '',
        'data: {"id":"123","choices":[{"delta":{}}],"usage":{"prompt_tokens":10,"completion_tokens":5,"total_tokens":15}}',
        '',
        'data: [DONE]',
        '',
    ]
    result = parse_sse_stream(_make_iterator(lines))
    assert result.usage == {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    assert result.model is None
    print("  [OK] test_openai_stream_with_usage")


def test_anthropic_stream():
    lines = [
        'event: content_block_delta',
        'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Hello"}}',
        '',
        'event: content_block_delta',
        'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":" world"}}',
        '',
        'data: [DONE]',
        '',
    ]
    result = parse_sse_stream(_make_iterator(lines))
    assert result.success
    assert "Hello" in result.content
    assert "world" in result.content
    assert len(result.events) == 3  # 2 content_block_delta + 1 [DONE]
    print("  [OK] test_anthropic_stream")


def test_error_event():
    lines = [
        'data: {"error":{"message":"Rate limit exceeded","type":"rate_limit_error"}}',
        '',
    ]
    result = parse_sse_stream(_make_iterator(lines))
    assert not result.success
    assert "Rate limit" in (result.error or "")
    print("  [OK] test_error_event")


def test_model_extraction():
    lines = [
        'data: {"id":"123","model":"gpt-4o-2024-08-06","choices":[{"delta":{"content":"Hi"}}]}',
        '',
        'data: [DONE]',
        '',
    ]
    result = parse_sse_stream(_make_iterator(lines))
    assert result.model == "gpt-4o-2024-08-06"
    print("  [OK] test_model_extraction")


def test_multiline_data():
    lines = [
        'data: {"id":"123","object":"chat.completion.chunk","choices":[{"delta":{"role":"assistant"}}]}',
        '',
        'data: {"id":"123","choices":[{"delta":{"content":"Hello"}}]}',
        '',
        'data: [DONE]',
        '',
    ]
    result = parse_sse_stream(_make_iterator(lines))
    assert result.success
    assert result.content == "Hello"
    print("  [OK] test_multiline_data")


if __name__ == "__main__":
    print("Testing sse_parser.py...")
    test_empty_stream()
    test_simple_openai_stream()
    test_openai_stream_with_usage()
    test_anthropic_stream()
    test_error_event()
    test_model_extraction()
    test_multiline_data()
    print("All sse_parser tests passed!")
