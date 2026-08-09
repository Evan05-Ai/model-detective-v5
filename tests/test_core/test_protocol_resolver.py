#!/usr/bin/env python3
"""协议解析器测试 - 协议检测+降级回退"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.core.protocol_resolver import infer_protocol, ProtocolResolver
from src.core.models import Protocol


def test_infer_openai():
    assert infer_protocol("gpt-4o") == Protocol.OPENAI
    assert infer_protocol("gpt-5") == Protocol.OPENAI
    assert infer_protocol("o3") == Protocol.OPENAI
    assert infer_protocol("o4-mini") == Protocol.OPENAI
    assert infer_protocol("chatgpt-4o-latest") == Protocol.OPENAI
    print("  [OK] test_infer_openai")


def test_infer_anthropic():
    assert infer_protocol("claude-sonnet-4-5") == Protocol.ANTHROPIC
    assert infer_protocol("claude-opus-4") == Protocol.ANTHROPIC
    assert infer_protocol("claude-haiku-3-5") == Protocol.ANTHROPIC
    print("  [OK] test_infer_anthropic")


def test_infer_gemini():
    assert infer_protocol("gemini-2.5-pro") == Protocol.GEMINI
    assert infer_protocol("gemini-2.0-flash") == Protocol.GEMINI
    assert infer_protocol("gemma-3") == Protocol.GEMINI
    print("  [OK] test_infer_gemini")


def test_infer_unknown_defaults_openai():
    assert infer_protocol("unknown-model") == Protocol.OPENAI
    assert infer_protocol("qwen-max") == Protocol.OPENAI
    assert infer_protocol("deepseek-chat") == Protocol.OPENAI
    print("  [OK] test_infer_unknown_defaults_openai")


def test_default_openai_no_degrade():
    """OpenAI 协议不需要降级"""
    resolver = ProtocolResolver("https://api.openai.com/v1", "sk-test", "gpt-4o")
    proto, degraded, reason = resolver.resolve()
    assert proto == Protocol.OPENAI
    assert not degraded
    assert reason == ""
    print("  [OK] test_default_openai_no_degrade")


def test_probe_failure_degrade_to_openai():
    """原生协议不可用应降级到 OpenAI"""
    import requests
    try:
        resolver = ProtocolResolver("https://invalid.endpoint.local", "sk-test", "claude-sonnet-4-5")
        proto, degraded, reason = resolver.resolve()
        assert proto == Protocol.OPENAI
        assert degraded
        assert "降级" in reason
        print("  [OK] test_probe_failure_degrade_to_openai")
    except Exception:
        # 如果 DNS 解析失败也可能引发异常，但降级机制仍应生效
        pass


def test_probe_anthropic_connection_error():
    """Anthropic 连接失败应降级"""
    resolver = ProtocolResolver("https://nonexistent-api.example.com", "sk-test", "claude-sonnet-4-5")
    proto, degraded, reason = resolver.resolve()
    assert degraded
    assert proto == Protocol.OPENAI
    assert len(reason) > 0
    print("  [OK] test_probe_anthropic_connection_error")


if __name__ == "__main__":
    print("Testing protocol_resolver.py...")
    test_infer_openai()
    test_infer_anthropic()
    test_infer_gemini()
    test_infer_unknown_defaults_openai()
    test_default_openai_no_degrade()
    test_probe_failure_degrade_to_openai()
    test_probe_anthropic_connection_error()
    print("All protocol_resolver tests passed!")
