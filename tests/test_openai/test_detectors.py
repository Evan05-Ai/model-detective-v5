#!/usr/bin/env python3
"""OpenAI 协议检测器测试"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.core.models import DetectorCategory, IssueLevel, Protocol
from src.protocols.openai.config import WEIGHTS, CATEGORIES, DETECTOR_MODES, validate_weights

from src.protocols.openai.detectors import build_active_detectors, build_passive_detectors


class MockOpenAIClient:
    """模拟 OpenAI 客户端"""
    def __init__(self, model="gpt-4o"):
        self.model = model
        self.calls = []

    def chat(self, messages=None, max_tokens=100, temperature=0.1,
             tools=None, response_format=None, detector_name="", **kwargs):
        self.calls.append(detector_name)
        from src.protocols.base_client import TokenUsage, ProtocolResponse
        usage = TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30)
        raw = {
            "id": "chatcmpl-xxx",
            "object": "chat.completion",
            "created": 1234567890,
            "model": self.model,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": "hello"},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        }

        # 如果带了 tools，模拟返回 tool_calls
        if tools:
            raw["choices"][0]["message"]["tool_calls"] = [{
                "id": "call_abc123",
                "function": {"name": "get_weather", "arguments": '{"location":"Tokyo"}'},
            }]

        # 如果带了 response_format，模拟返回结构化 JSON
        if response_format:
            raw["choices"][0]["message"]["content"] = '{"name":"John","age":30,"city":"New York"}'

        return ProtocolResponse(
            success=True,
            content=raw["choices"][0]["message"]["content"],
            model=self.model,
            headers={"server": "openai", "x-oneapi-request-id": "xyz"},
            usage=usage,
            status_code=200,
            raw_response=raw,
        )

    def chat_stream(self, **kwargs):
        return self.chat(**kwargs)

    def list_models(self):
        return True, ["gpt-4o", "gpt-4o-mini", "gpt-5"], ""

    def get_cost_summary(self):
        return {"total_tokens": 30, "total_requests": 1, "estimated_cost_usd": 0.001}


def test_detector_weights_sum_to_one():
    """OpenAI 权重和应为 1.0"""
    total = sum(WEIGHTS.values())
    assert abs(total - 1.0) < 0.01, f"Weight sum: {total}"
    print("  [OK] test_detector_weights_sum_to_one")


def test_detector_categories_defined():
    """所有检测器应有分类"""
    for name in WEIGHTS:
        assert name in CATEGORIES, f"{name} missing category"
    print("  [OK] test_detector_categories_defined")


def test_validate_weights():
    """OpenAI 配置启动校验应通过"""
    validate_weights()
    assert set(WEIGHTS) == set(CATEGORIES) == set(DETECTOR_MODES)
    print("  [OK] test_validate_weights")





def test_build_active_detectors():
    """构建 ActiveDetector"""
    dets = build_active_detectors()
    names = [d.name for d in dets]
    assert "basic_request" in names
    assert "model_consistency" in names
    assert "function_calling" in names
    assert "protocol" in names
    assert "token_billing" in names
    assert "long_context" not in names  # 默认不包含
    print("  [OK] test_build_active_detectors")


def test_build_with_long_context():
    """启用 long_context"""
    dets = build_active_detectors(long_context=True)
    names = [d.name for d in dets]
    assert "long_context" in names
    print("  [OK] test_build_with_long_context")


def test_build_passive_detectors():
    """构建 PassiveDetector"""
    dets = build_passive_detectors()
    names = [d.name for d in dets]
    assert "integrity" in names
    print("  [OK] test_build_passive_detectors")


def test_basic_request_detector():
    """BasicRequestDetector 执行"""
    from src.protocols.openai.detectors.basic_request import BasicRequestDetector
    det = BasicRequestDetector()
    client = MockOpenAIClient()
    result = det.run(client)

    assert result.name == "basic_request"
    assert result.category == DetectorCategory.AUTHENTICITY
    assert 0 <= result.score <= 100
    assert result.status == "pass"
    print(f"  [OK] test_basic_request_detector (score={result.score})")


def test_model_consistency_detector():
    """ModelConsistencyDetector 执行"""
    from src.protocols.openai.detectors.model_consistency import ModelConsistencyDetector
    det = ModelConsistencyDetector()
    client = MockOpenAIClient()
    result = det.run(client)

    assert result.name == "model_consistency"
    assert 0 <= result.score <= 100
    print(f"  [OK] test_model_consistency_detector (score={result.score})")


def test_function_calling_detector():
    """FunctionCallingDetector 执行"""
    from src.protocols.openai.detectors.function_calling import FunctionCallingDetector
    det = FunctionCallingDetector()
    client = MockOpenAIClient()
    result = det.run(client)

    assert result.name == "function_calling"
    assert result.score == 100, f"Expected 100 with valid tool_calls, got {result.score}"
    print(f"  [OK] test_function_calling_detector (score={result.score})")


def test_structured_output_detector():
    """StructuredOutputDetector 执行"""
    from src.protocols.openai.detectors.structured_output import StructuredOutputDetector
    det = StructuredOutputDetector()
    client = MockOpenAIClient()
    result = det.run(client)

    assert result.name == "structured_output"
    assert result.score == 100, f"Expected 100 with valid JSON, got {result.score}"
    print(f"  [OK] test_structured_output_detector (score={result.score})")


def test_protocol_detector():
    """ProtocolDetector 执行"""
    from src.protocols.openai.detectors.protocol import ProtocolDetector
    det = ProtocolDetector()
    client = MockOpenAIClient()
    result = det.run(client)

    assert result.name == "protocol"
    assert result.score > 0, f"Expected score > 0, got {result.score}"
    print(f"  [OK] test_protocol_detector (score={result.score})")


def test_token_billing_detector():
    """TokenBillingDetector 执行"""
    from src.protocols.openai.detectors.token_billing import TokenBillingDetector
    det = TokenBillingDetector()
    client = MockOpenAIClient()
    result = det.run(client)

    assert result.name == "token_billing"
    assert result.score > 0, f"Expected score > 0, got {result.score}"
    print(f"  [OK] test_token_billing_detector (score={result.score})")


def test_detector_mode_assignment():
    """检测器模式分配"""
    for name, modes in DETECTOR_MODES.items():
        valid_modes = {"quick", "standard", "full"}
        assert any(m in valid_modes for m in modes), f"{name} has no valid mode"
    print("  [OK] test_detector_mode_assignment")


class MockBillingOpenAIClient:
    """Mock client with realistic token counts for billing_integrity test"""
    def __init__(self, model="gpt-4o"):
        self.model = model

    def chat(self, messages=None, max_tokens=100, temperature=0.1,
             tools=None, response_format=None, detector_name="", **kwargs):
        from src.protocols.base_client import TokenUsage, ProtocolResponse
        from src.utils.token_counter import count_tokens, OPENAI_MESSAGE_OVERHEAD
        prompt = messages[0]["content"] if messages else ""
        est_input = count_tokens(prompt) + OPENAI_MESSAGE_OVERHEAD
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
    from src.protocols.openai.detectors.billing_integrity import BillingIntegrityDetector
    det = BillingIntegrityDetector()
    client = MockBillingOpenAIClient()
    result = det.run(client)

    assert result.name == "billing_integrity"
    assert 0 <= result.score <= 100
    assert result.cost_tokens > 0
    assert len(result.issues) > 0
    # With accurate billing, score should be high
    assert result.score >= 80, f"Accurate billing should score high, got {result.score}"
    print(f"  [OK] test_billing_integrity_detector (score={result.score})")


def test_billing_integrity_inflated():
    """BillingIntegrityDetector with inflated token counts"""
    from src.protocols.openai.detectors.billing_integrity import BillingIntegrityDetector
    det = BillingIntegrityDetector()
    client = MockOpenAIClient()  # returns prompt_tokens=10, completion_tokens=20
    result = det.run(client)

    assert result.name == "billing_integrity"
    assert 0 <= result.score <= 100
    assert len(result.issues) > 0
    # With inflated billing, should have issues
    has_non_ok = any(i.level != IssueLevel.OK for i in result.issues)
    assert has_non_ok, "Inflated billing should trigger issues"
    print(f"  [OK] test_billing_integrity_inflated (score={result.score})")


if __name__ == "__main__":
    print("Testing OpenAI detectors...")
    test_detector_weights_sum_to_one()
    test_detector_categories_defined()
    test_validate_weights()
    test_build_active_detectors()

    test_build_with_long_context()
    test_build_passive_detectors()
    test_basic_request_detector()
    test_model_consistency_detector()
    test_function_calling_detector()
    test_structured_output_detector()
    test_protocol_detector()
    test_token_billing_detector()
    test_billing_integrity_detector()
    test_billing_integrity_inflated()
    test_detector_mode_assignment()
    print("All OpenAI detector tests passed!")
