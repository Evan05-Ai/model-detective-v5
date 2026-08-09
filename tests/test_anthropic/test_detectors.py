#!/usr/bin/env python3
"""Anthropic 协议检测器测试"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.core.models import DetectorCategory, IssueLevel, Protocol
from src.protocols.anthropic.config import WEIGHTS, CATEGORIES, DETECTOR_MODES, validate_weights
from src.protocols.anthropic.detectors import build_active_detectors, build_passive_detectors



class MockAnthropicClient:
    """模拟 Anthropic 客户端"""
    def __init__(self, model="claude-sonnet-4-5", has_signature=True, has_proxy_headers=False):
        self.model = model
        self.has_signature = has_signature
        self.has_proxy_headers = has_proxy_headers
        self.calls = []

    def messages(self, messages=None, max_tokens=100, temperature=0.1,
                 system=None, tools=None, thinking=None, tool_choice=None,
                 detector_name="", **kwargs):
        self.calls.append(detector_name)
        from src.protocols.base_client import TokenUsage, ProtocolResponse
        usage = TokenUsage(prompt_tokens=15, completion_tokens=25, total_tokens=40)

        content_blocks = [{"type": "text", "text": "hello world"}]
        if thinking:
            content_blocks.insert(0, {
                "type": "thinking",
                "thinking": "Let me think about this... 17 * 23 = 391",
            })
            if self.has_signature:
                content_blocks[0]["signature"] = "valid_signature_abc123"

        raw = {
            "id": "msg_abc123def",
            "type": "message",
            "role": "assistant",
            "content": content_blocks,
            "model": self.model,
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {"input_tokens": 15, "output_tokens": 25},
        }

        headers = {"server": "cloudflare"}
        if self.has_proxy_headers:
            headers["x-oneapi-request-id"] = "proxy123"

        return ProtocolResponse(
            success=True,
            content="hello world",
            model=self.model,
            headers=headers,
            usage=usage,
            status_code=200,
            raw_response=raw,
            thinking="Let me think..." if thinking else None,
            thinking_signature="valid_signature_abc123" if (thinking and self.has_signature) else None,
            message_id="msg_abc123def",
        )

    def get_cost_summary(self):
        return {"total_tokens": 40, "total_requests": 1, "estimated_cost_usd": 0.001}


def test_detector_weights_sum_to_one():
    """Anthropic 权重和应为 1.0"""
    total = sum(WEIGHTS.values())
    assert abs(total - 1.0) < 0.01, f"Weight sum: {total}"
    print("  [OK] test_detector_weights_sum_to_one")


def test_detector_categories_defined():
    """所有检测器应有分类"""
    for name in WEIGHTS:
        assert name in CATEGORIES, f"{name} missing category"
    print("  [OK] test_detector_categories_defined")


def test_validate_weights():
    """Anthropic 配置启动校验应通过"""
    validate_weights()
    assert set(WEIGHTS) == set(CATEGORIES) == set(DETECTOR_MODES)
    print("  [OK] test_validate_weights")


def test_detector_registry_matches_config():
    """注册检测器应全部受配置表约束。"""
    names = {d.name for d in build_active_detectors(long_context=True)} | {d.name for d in build_passive_detectors()}
    assert names == set(WEIGHTS) == set(CATEGORIES) == set(DETECTOR_MODES)
    print("  [OK] test_detector_registry_matches_config")


def test_build_active_detectors():

    """构建 ActiveDetector"""
    dets = build_active_detectors()
    names = [d.name for d in dets]
    assert "identity" in names
    assert "thinking_signature" in names
    assert "behavioral_signature" in names
    assert "consistency" in names
    assert "knowledge" in names
    assert "protocol" in names
    assert "function_calling" in names
    assert "message_id" in names
    assert "token_usage" in names
    assert "pdf" in names
    assert "structured_output" in names
    assert "billing_integrity" in names  # v2.2 新增
    assert "long_context" not in names  # 默认不包含
    assert len(dets) == 12
    print("  [OK] test_build_active_detectors")


def test_build_with_long_context():
    """启用 long_context"""
    dets = build_active_detectors(long_context=True)
    assert len(dets) == 13
    names = [d.name for d in dets]
    assert "long_context" in names
    print("  [OK] test_build_with_long_context")


def test_build_passive_detectors():
    """构建 PassiveDetector"""
    dets = build_passive_detectors()
    names = [d.name for d in dets]
    assert "integrity" in names
    print("  [OK] test_build_passive_detectors")


def test_identity_detector():
    """IdentityDetector"""
    from src.protocols.anthropic.detectors.identity import IdentityDetector
    det = IdentityDetector()
    client = MockAnthropicClient()
    result = det.run(client)

    assert result.name == "identity"
    assert result.category == DetectorCategory.AUTHENTICITY
    assert 0 <= result.score <= 100
    print(f"  [OK] test_identity_detector (score={result.score})")


def test_thinking_signature_with_proxy():
    """thinking_signature 应检测到代理头"""
    from src.protocols.anthropic.detectors.thinking_signature import ThinkingSignatureDetector
    det = ThinkingSignatureDetector()
    # 有签名 + 有代理头
    client = MockAnthropicClient(has_signature=True, has_proxy_headers=True)
    result = det.run(client)

    assert result.name == "thinking_signature"
    # 有签名 + 无代理头 = 100; 有签名 + 有代理头 = 70
    assert result.score == 70, f"Expected 70 (signature+proxy), got {result.score}"
    has_minor = any(i.level == IssueLevel.MINOR for i in result.issues)
    assert has_minor, "应有 MINOR issue 提示中转站转发"
    print(f"  [OK] test_thinking_signature_with_proxy (score={result.score})")


def test_thinking_signature_direct():
    """thinking_signature 直连（无代理头）"""
    from src.protocols.anthropic.detectors.thinking_signature import ThinkingSignatureDetector
    det = ThinkingSignatureDetector()
    client = MockAnthropicClient(has_signature=True, has_proxy_headers=False)
    result = det.run(client)

    assert result.score == 100, f"Expected 100 (direct), got {result.score}"
    has_ok = any(i.level == IssueLevel.OK for i in result.issues)
    assert has_ok, "应有 OK issue"
    print(f"  [OK] test_thinking_signature_direct (score={result.score})")


def test_thinking_signature_missing():
    """thinking_signature 缺失"""
    from src.protocols.anthropic.detectors.thinking_signature import ThinkingSignatureDetector
    det = ThinkingSignatureDetector()
    client = MockAnthropicClient(has_signature=False)
    result = det.run(client)

    assert result.score < 50, f"Expected low score without signature, got {result.score}"
    has_critical = any(i.level == IssueLevel.CRITICAL for i in result.issues)
    assert has_critical, "缺失签名应有 CRITICAL issue"
    print(f"  [OK] test_thinking_signature_missing (score={result.score})")


def test_protocol_detector():
    """ProtocolDetector"""
    from src.protocols.anthropic.detectors.protocol import ProtocolDetector
    det = ProtocolDetector()
    client = MockAnthropicClient()
    result = det.run(client)

    assert result.name == "protocol"
    assert result.score > 0
    print(f"  [OK] test_protocol_detector (score={result.score})")


def test_message_id_detector():
    """MessageIdDetector"""
    from src.protocols.anthropic.detectors.message_id import MessageIdDetector
    det = MessageIdDetector()
    client = MockAnthropicClient()
    result = det.run(client)

    assert result.name == "message_id"
    assert result.score > 0
    print(f"  [OK] test_message_id_detector (score={result.score})")


def test_function_calling_detector():
    """FunctionCallingDetector - 需要模拟 tool_use block"""
    from src.protocols.anthropic.detectors.function_calling import FunctionCallingDetector
    det = FunctionCallingDetector()
    client = MockAnthropicClient()

    # 覆盖 messages 方法返回 tool_use
    original = client.messages
    def _patched(*args, **kwargs):
        resp = original(*args, **kwargs)
        resp.raw_response["content"] = [{
            "type": "tool_use",
            "id": "toolu_abc123",
            "name": "get_weather",
            "input": {"location": "Paris"},
        }]
        return resp
    client.messages = _patched

    result = det.run(client)
    assert result.name == "function_calling"
    assert result.score >= 95, f"Expected high score for valid tool_use, got {result.score}"
    print(f"  [OK] test_function_calling_detector (score={result.score})")


def test_knowledge_detector():
    """KnowledgeDetector"""
    from src.protocols.anthropic.detectors.knowledge import KnowledgeDetector
    det = KnowledgeDetector()
    client = MockAnthropicClient()
    result = det.run(client)

    assert result.name == "knowledge"
    assert 0 <= result.score <= 100
    print(f"  [OK] test_knowledge_detector (score={result.score})")


def test_token_usage_detector():
    """TokenUsageDetector"""
    from src.protocols.anthropic.detectors.token_usage import TokenUsageDetector
    det = TokenUsageDetector()
    client = MockAnthropicClient()
    result = det.run(client)

    assert result.name == "token_usage"
    assert result.score > 0
    print(f"  [OK] test_token_usage_detector (score={result.score})")


def test_weight_thinking_signature_highest():
    """thinking_signature 权重最高"""
    assert WEIGHTS["thinking_signature"] == 0.25
    max_weight = max(WEIGHTS.values())
    assert WEIGHTS["thinking_signature"] == max_weight
    print("  [OK] test_weight_thinking_signature_highest")


class MockBillingAnthropicClient:
    """Mock client with realistic token counts for billing_integrity test"""
    def __init__(self, model="claude-sonnet-4-5"):
        self.model = model

    def messages(self, messages=None, max_tokens=100, temperature=0.1,
                 system=None, tools=None, thinking=None, tool_choice=None,
                 detector_name="", **kwargs):
        from src.protocols.base_client import TokenUsage, ProtocolResponse
        from src.utils.token_counter import count_tokens, ANTHROPIC_MESSAGE_OVERHEAD
        prompt = messages[0]["content"] if messages else ""
        est_input = count_tokens(prompt) + ANTHROPIC_MESSAGE_OVERHEAD
        content = "AI dreams in silicon sleep,\nBytes flow like quiet streams,\nLogic wakes from deep."
        est_output = count_tokens(content)
        usage = TokenUsage(
            prompt_tokens=est_input,
            completion_tokens=est_output,
            total_tokens=est_input + est_output,
        )
        return ProtocolResponse(
            success=True, content=content, model=self.model,
            headers={}, usage=usage, status_code=200, raw_response={},
        )

    def get_cost_summary(self):
        return {"total_tokens": 50, "total_requests": 1, "estimated_cost_usd": 0.001}


def test_billing_integrity_detector():
    """BillingIntegrityDetector with accurate billing"""
    from src.protocols.anthropic.detectors.billing_integrity import BillingIntegrityDetector
    det = BillingIntegrityDetector()
    client = MockBillingAnthropicClient()
    result = det.run(client)

    assert result.name == "billing_integrity"
    assert 0 <= result.score <= 100
    assert result.cost_tokens > 0
    assert len(result.issues) > 0
    assert result.score >= 80, f"Accurate billing should score high, got {result.score}"
    print(f"  [OK] test_billing_integrity_detector (score={result.score})")


def test_billing_integrity_inflated():
    """BillingIntegrityDetector with inflated token counts"""
    from src.protocols.anthropic.detectors.billing_integrity import BillingIntegrityDetector
    det = BillingIntegrityDetector()
    client = MockAnthropicClient()  # returns prompt_tokens=15, completion_tokens=25
    result = det.run(client)

    assert result.name == "billing_integrity"
    assert 0 <= result.score <= 100
    assert len(result.issues) > 0
    has_non_ok = any(i.level != IssueLevel.OK for i in result.issues)
    assert has_non_ok, "Inflated billing should trigger issues"
    print(f"  [OK] test_billing_integrity_inflated (score={result.score})")


if __name__ == "__main__":
    print("Testing Anthropic detectors...")
    test_detector_weights_sum_to_one()
    test_detector_categories_defined()
    test_validate_weights()
    test_detector_registry_matches_config()
    test_build_active_detectors()
    test_build_with_long_context()
    test_build_passive_detectors()
    test_identity_detector()
    test_thinking_signature_with_proxy()
    test_thinking_signature_direct()
    test_thinking_signature_missing()
    test_protocol_detector()
    test_message_id_detector()
    test_function_calling_detector()
    test_knowledge_detector()
    test_token_usage_detector()
    test_billing_integrity_detector()
    test_billing_integrity_inflated()
    test_weight_thinking_signature_highest()
    print("All Anthropic detector tests passed!")
