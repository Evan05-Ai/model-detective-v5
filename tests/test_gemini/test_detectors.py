#!/usr/bin/env python3
"""Gemini 协议检测器测试"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.core.models import DetectorCategory, IssueLevel, Protocol
from src.protocols.gemini.config import WEIGHTS, CATEGORIES, DETECTOR_MODES, validate_weights

from src.protocols.gemini.detectors import build_active_detectors, build_passive_detectors


class MockGeminiClient:
    """模拟 Gemini 客户端"""
    def __init__(self, model="gemini-2.5-pro"):
        self.model = model
        self.calls = []

    def generate(self, contents=None, max_tokens=100, temperature=0.1,
                  tools=None, response_schema=None, detector_name="", **kwargs):
        self.calls.append(detector_name)
        from src.protocols.base_client import TokenUsage, ProtocolResponse
        usage = TokenUsage(prompt_tokens=10, completion_tokens=15, total_tokens=25)

        # 模拟 function calling 响应
        if tools:
            raw = {
                "candidates": [{
                    "content": {
                        "parts": [{
                            "functionCall": {
                                "name": "get_weather",
                                "args": {"location": "Tokyo"},
                            }
                        }],
                        "role": "model",
                    },
                    "finishReason": "STOP",
                }],
                "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 15, "totalTokenCount": 25},
            }
        elif response_schema:
            raw = {
                "candidates": [{
                    "content": {
                        "parts": [{"text": '{"name":"John","age":30,"city":"New York"}'}],
                        "role": "model",
                    },
                    "finishReason": "STOP",
                }],
                "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 15, "totalTokenCount": 25},
            }
        else:
            raw = {
                "candidates": [{
                    "content": {
                        "parts": [{"text": "hello world"}],
                        "role": "model",
                    },
                    "finishReason": "STOP",
                }],
                "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 15, "totalTokenCount": 25},
            }

        return ProtocolResponse(
            success=True,
            content=raw["candidates"][0]["content"]["parts"][0].get("text", ""),
            model=self.model,
            headers={"server": "google"},
            usage=usage,
            status_code=200,
            raw_response=raw,
        )

    def generate_stream(self, **kwargs):
        return self.generate(**kwargs)

    def list_models(self):
        return True, [self.model, "gemini-2.0-flash", "gemini-1.5-pro"], ""

    def get_cost_summary(self):
        return {"total_tokens": 25, "total_requests": 1, "estimated_cost_usd": 0.001}


def test_detector_weights_sum_to_one():
    """Gemini 权重和应为 1.0"""
    total = sum(WEIGHTS.values())
    assert abs(total - 1.0) < 0.01, f"Weight sum: {total}"
    print("  [OK] test_detector_weights_sum_to_one")


def test_detector_categories_defined():
    """所有检测器应有分类"""
    for name in WEIGHTS:
        assert name in CATEGORIES, f"{name} missing category"
    print("  [OK] test_detector_categories_defined")


def test_validate_weights():
    """Gemini 配置启动校验应通过"""
    validate_weights()
    assert set(WEIGHTS) == set(CATEGORIES) == set(DETECTOR_MODES)
    print("  [OK] test_validate_weights")


def test_build_active_detectors():

    """构建 ActiveDetector"""
    dets = build_active_detectors()
    names = [d.name for d in dets]
    assert "basic_request" in names
    assert "model_info" in names
    assert "function_calling" in names
    assert "structured_output" in names
    assert "protocol" in names
    assert "token_usage" in names
    assert len(dets) == 7  # 6 original + billing_integrity
    print("  [OK] test_build_active_detectors")


def test_build_passive_detectors():
    """构建 PassiveDetector"""
    dets = build_passive_detectors()
    names = [d.name for d in dets]
    assert "integrity" in names
    print("  [OK] test_build_passive_detectors")


def test_basic_request_detector():
    """BasicRequestDetector"""
    from src.protocols.gemini.detectors.basic_request import BasicRequestDetector
    det = BasicRequestDetector()
    client = MockGeminiClient()
    result = det.run(client)

    assert result.name == "basic_request"
    assert result.category == DetectorCategory.AUTHENTICITY
    assert 0 <= result.score <= 100
    print(f"  [OK] test_basic_request_detector (score={result.score})")


def test_model_info_detector():
    """ModelInfoDetector"""
    from src.protocols.gemini.detectors.model_info import ModelInfoDetector
    det = ModelInfoDetector()
    client = MockGeminiClient()
    result = det.run(client)

    assert result.name == "model_info"
    assert result.category == DetectorCategory.AUTHENTICITY
    assert result.score > 50, f"Expected score > 50 for matching model, got {result.score}"
    print(f"  [OK] test_model_info_detector (score={result.score})")


def test_protocol_detector():
    """ProtocolDetector"""
    from src.protocols.gemini.detectors.protocol import ProtocolDetector
    det = ProtocolDetector()
    client = MockGeminiClient()
    result = det.run(client)

    assert result.name == "protocol"
    assert result.score > 50, f"Expected score > 50, got {result.score}"
    print(f"  [OK] test_protocol_detector (score={result.score})")


def test_function_calling_detector():
    """FunctionCallingDetector"""
    from src.protocols.gemini.detectors.function_calling import FunctionCallingDetector
    det = FunctionCallingDetector()
    client = MockGeminiClient()
    result = det.run(client)

    assert result.name == "function_calling"
    assert result.score == 100, f"Expected 100 with valid functionCall, got {result.score}"
    print(f"  [OK] test_function_calling_detector (score={result.score})")


def test_structured_output_detector():
    """StructuredOutputDetector"""
    from src.protocols.gemini.detectors.structured_output import StructuredOutputDetector
    det = StructuredOutputDetector()
    client = MockGeminiClient()
    result = det.run(client)

    assert result.name == "structured_output"
    assert result.score == 100, f"Expected 100 with valid JSON, got {result.score}"
    print(f"  [OK] test_structured_output_detector (score={result.score})")


def test_token_usage_detector():
    """TokenUsageDetector"""
    from src.protocols.gemini.detectors.token_usage import TokenUsageDetector
    det = TokenUsageDetector()
    client = MockGeminiClient()
    result = det.run(client)

    assert result.name == "token_usage"
    assert result.score > 50, f"Expected score > 50, got {result.score}"
    print(f"  [OK] test_token_usage_detector (score={result.score})")


def test_function_calling_weight_highest():
    """Gemini 中 function_calling 权重最高"""
    assert WEIGHTS["function_calling"] == 0.18
    max_weight = max(WEIGHTS.values())
    assert WEIGHTS["function_calling"] == max_weight
    print("  [OK] test_function_calling_weight_highest")


class MockBillingGeminiClient:
    """Mock client with realistic token counts for billing_integrity test"""
    def __init__(self, model="gemini-2.5-pro"):
        self.model = model

    def generate(self, contents=None, max_tokens=100, temperature=0.1,
                  tools=None, response_schema=None, detector_name="", **kwargs):
        from src.protocols.base_client import TokenUsage, ProtocolResponse
        from src.utils.token_counter import count_tokens, ANTHROPIC_MESSAGE_OVERHEAD
        prompt = ""
        if contents and contents[0].get("parts"):
            prompt = contents[0]["parts"][0].get("text", "")
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
    from src.protocols.gemini.detectors.billing_integrity import BillingIntegrityDetector
    det = BillingIntegrityDetector()
    client = MockBillingGeminiClient()
    result = det.run(client)

    assert result.name == "billing_integrity"
    assert 0 <= result.score <= 100
    assert result.cost_tokens > 0
    assert len(result.issues) > 0
    assert result.score >= 80, f"Accurate billing should score high, got {result.score}"
    print(f"  [OK] test_billing_integrity_detector (score={result.score})")


def test_billing_integrity_inflated():
    """BillingIntegrityDetector with inflated token counts"""
    from src.protocols.gemini.detectors.billing_integrity import BillingIntegrityDetector
    det = BillingIntegrityDetector()
    client = MockGeminiClient()  # returns prompt_tokens=10, completion_tokens=15
    result = det.run(client)

    assert result.name == "billing_integrity"
    assert 0 <= result.score <= 100
    assert len(result.issues) > 0
    has_non_ok = any(i.level != IssueLevel.OK for i in result.issues)
    assert has_non_ok, "Inflated billing should trigger issues"
    print(f"  [OK] test_billing_integrity_inflated (score={result.score})")


if __name__ == "__main__":
    print("Testing Gemini detectors...")
    test_detector_weights_sum_to_one()
    test_detector_categories_defined()
    test_validate_weights()
    test_build_active_detectors()

    test_build_passive_detectors()
    test_basic_request_detector()
    test_model_info_detector()
    test_protocol_detector()
    test_function_calling_detector()
    test_structured_output_detector()
    test_token_usage_detector()
    test_billing_integrity_detector()
    test_billing_integrity_inflated()
    test_function_calling_weight_highest()
    print("All Gemini detector tests passed!")
