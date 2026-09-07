#!/usr/bin/env python3
"""v3.0.3 预算信封化测试：检测深度不再受中转站上报数字影响

复现两类线上实测场景：
- Kiro 类（09-06）：每请求上报 ~45k cache_read_input_tokens
- beiluoxi 类（09-07）：每请求上报 ~48k 普通 input/cache_creation
两类站在旧预算模型下都导致 2-3 个请求即"耗尽"100k 预算、10/13 检测器
SKIP。v3.0.3 起预算唯一口径是"请求信封"（我方 payload 估算），上报
数字仅用于展示与费用兜底。
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.core.detector_base import ActiveDetector
from src.core.models import CheckResultV2, DetectorCategory, RunMode, Protocol
from src.core.runner import Runner
from src.core.scorer import calculate_scores
from src.protocols.base_client import TokenUsage, BaseProtocolClient, ProtocolResponse
from src.protocols.openai.client import OpenAIClient
from src.protocols.anthropic.client import AnthropicClient


# ==================== 信封计量 ====================

def test_envelope_is_budget_and_reported_is_not():
    """预算口径 = 请求信封；上报数字（无论多大）不入预算"""
    c = AnthropicClient("https://relay.test", "sk-test-123456", "claude-opus-4-5")
    payload = {"model": "claude-opus-4-5", "max_tokens": 100,
               "messages": [{"role": "user", "content": "Hi"}]}
    est = c._add_envelope(payload)
    assert 5 <= est <= 200, f"小 payload 信封应在合理范围，实际 {est}"

    # beiluoxi 类上报：普通 input 虚增 4.8 万
    c._record_usage(TokenUsage(prompt_tokens=48000, completion_tokens=50,
                               total_tokens=48050, cost_input_equiv=48000))
    # Kiro 类上报：cache_read 4.5 万
    c._record_usage(TokenUsage(prompt_tokens=200, completion_tokens=50,
                               total_tokens=45250, cache_read_input_tokens=45000,
                               cost_input_equiv=200 + 0.1 * 45000))

    # 预算 = 信封（仅 1 个小请求），与上报的 9 万+ 无关
    assert c.get_budget_tokens() == est
    # 展示口径 = 上报总量
    assert c.get_cost_summary()["total_tokens"] == 48050 + 45250
    print("  [OK] envelope budget immune to reported inflation")


def test_billable_cost_discounts():
    """费用兜底口径：缓存写入 1.25x、读取 0.1x、OpenAI 命中半价"""
    # Anthropic: input 200 + 1.25×1000(cc) + 0.1×45000(cr) = 5950 当量
    c = AnthropicClient("https://relay.test", "sk-test-123456", "gpt-4o")  # 用已知价模型
    c._record_usage(TokenUsage(prompt_tokens=200, completion_tokens=0, total_tokens=46200,
                               cache_creation_input_tokens=1000,
                               cache_read_input_tokens=45000,
                               cost_input_equiv=200 + 1.25 * 1000 + 0.1 * 45000))
    # gpt-4o input $2.5/M → 5950×2.5/1M ≈ $0.0149
    assert abs(c.get_billable_cost_usd() - 5950 * 2.5 / 1_000_000) < 1e-9

    # OpenAI: prompt 1000, cached 900 → equiv 550
    u = OpenAIClient._parse_usage({"prompt_tokens": 1000, "completion_tokens": 0,
                                   "total_tokens": 1000,
                                   "prompt_tokens_details": {"cached_tokens": 900}})
    assert u.cached_tokens == 900
    assert abs(u.cost_input_equiv - 550.0) < 1e-9
    u2 = OpenAIClient._parse_usage({"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15})
    assert abs(u2.cost_input_equiv - 10.0) < 1e-9
    print("  [OK] billable cost discount formulas")


# ==================== Runner 集成（复现线上两类站） ====================

class RelayClient(BaseProtocolClient):
    """模拟中转站：复用真实信封/费用记账，messages() 按场景上报用量"""

    def __init__(self, scenario: str):
        super().__init__("https://relay.test", "sk-test-123456", "gpt-4o")
        self.scenario = scenario
        self.calls = 0

    def messages(self, **kwargs):
        self._add_envelope({"model": self.model, "messages": kwargs.get("messages", []),
                            "max_tokens": kwargs.get("max_tokens", 100)})
        self.calls += 1
        if self.scenario == "kiro_cache":
            usage = TokenUsage(prompt_tokens=200, completion_tokens=50, total_tokens=45250,
                               cache_read_input_tokens=45000,
                               cost_input_equiv=200 + 0.1 * 45000)
        elif self.scenario == "overhead_plain":
            usage = TokenUsage(prompt_tokens=48000, completion_tokens=50, total_tokens=48050,
                               cost_input_equiv=48000)
        else:  # honest
            usage = TokenUsage(prompt_tokens=60, completion_tokens=40, total_tokens=100,
                               cost_input_equiv=60)
        self._record_usage(usage)
        return ProtocolResponse(success=True, content="ok", model=self.model,
                                headers={}, usage=usage)


class TinyDetector(ActiveDetector):
    """每次运行发 1 个请求的迷你检测器"""
    weight = 0.1
    modes = ["quick", "standard", "full"]
    estimated_tokens = 600

    def __init__(self, name):
        self.name = name
        self.category = DetectorCategory.AUTHENTICITY

    def run(self, client) -> CheckResultV2:
        client.messages(detector_name=self.name)
        return CheckResultV2(name=self.name, category=self.category,
                             score=90, weight=self.weight, cost_tokens=0)


def _run(client, detectors, mode=RunMode.STANDARD):
    return Runner(client=client, active_detectors=detectors, passive_detectors=[],
                  protocol=Protocol.ANTHROPIC, model=client.model, mode=mode).run()


def test_kiro_relay_full_report():
    """Kiro 类站（45k cache_read/请求）：4 检测器全部运行，零 SKIP"""
    client = RelayClient("kiro_cache")
    report = _run(client, [TinyDetector(f"det_{i}") for i in range(4)])
    skips = [r for r in report.results if r.status == "skip"]
    assert not skips, f"不应有 SKIP: {[(r.name, r.details) for r in skips]}"
    assert client.calls == 5  # 1 preflight + 4 detectors
    print("  [OK] kiro relay: full report")


def test_overhead_relay_full_report():
    """beiluoxi 类站（48k plain input/请求）：检测深度不受上报影响。

    5 请求 × ~$0.12（gpt-4o 价）≈ $0.6 << $15 钱包上限 → 全跑完。
    opus 定价下同场景约 $3.6，同样低于上限。
    """
    client = RelayClient("overhead_plain")
    report = _run(client, [TinyDetector(f"det_{i}") for i in range(4)])
    skips = [r for r in report.results if r.status == "skip"]
    assert not skips, f"不应有 SKIP: {[(r.name, r.details) for r in skips]}"
    # 费用披露仍按上报口径累计（preflight + 4 检测器 = 5 请求 × 48k）
    assert client.get_cost_summary()["total_tokens"] == 5 * 48050
    print("  [OK] overhead relay: full report, cost still tracked")


def test_wallet_stop_on_absurd_reporting():
    """上报离谱（费用超钱包上限）→ 剩余组止损并给出明确消息"""
    class AbsurdRelay(RelayClient):
        def messages(self, **kwargs):
            self._add_envelope({"m": 1})
            self.calls += 1
            # 单请求 200 万 input ≈ $5 (gpt-4o) —— 2 个请求即超 QUICK $5 上限
            usage = TokenUsage(prompt_tokens=2_000_000, completion_tokens=0,
                               total_tokens=2_000_000, cost_input_equiv=2_000_000)
            self._record_usage(usage)
            return ProtocolResponse(success=True, content="ok", model=self.model,
                                    headers={}, usage=usage)

    from src.core.runner import DETECTOR_PRIORITY
    client = AbsurdRelay("honest")
    d1, d2 = TinyDetector("w1_a"), TinyDetector("w2_a")
    DETECTOR_PRIORITY["w1_a"] = 1
    DETECTOR_PRIORITY["w2_a"] = 2
    try:
        report = _run(client, [d1, d2], mode=RunMode.QUICK)  # QUICK 钱包 $5
    finally:
        DETECTOR_PRIORITY.pop("w1_a", None)
        DETECTOR_PRIORITY.pop("w2_a", None)
    by = {r.name: r for r in report.results}
    assert by["w1_a"].status == "pass"
    assert by["w2_a"].status == "skip"
    assert "费用保护" in by["w2_a"].details
    print("  [OK] wallet stop fires on absurd reporting")


def test_reservations_released_after_run():
    client = RelayClient("honest")
    runner_detectors = [TinyDetector(f"det_{i}") for i in range(3)]
    r = Runner(client=client, active_detectors=runner_detectors, passive_detectors=[],
               protocol=Protocol.ANTHROPIC, model=client.model, mode=RunMode.STANDARD)
    r.run()
    assert r._reserved_tokens == 0
    print("  [OK] reservations released")


# ==================== 维度分数 None 语义 ====================

def test_dimension_scores_none_when_no_effective():
    """维度内全部 skip 时该维度分数为 None（无数据 ≠ 0 分）"""
    skipped = CheckResultV2(name="fn", category=DetectorCategory.CAPABILITY,
                            score=0, weight=0.1, status="skip")
    auth = CheckResultV2(name="id", category=DetectorCategory.AUTHENTICITY,
                         score=90, weight=0.1, status="pass")
    s = calculate_scores([skipped, auth])
    assert s["capability_score"] is None
    assert s["authenticity_score"] == 90.0
    assert s["total_score"] > 0
    print("  [OK] empty dimension -> None (not 0.0)")


def test_dimension_scores_normal_path_unchanged():
    a = CheckResultV2(name="id", category=DetectorCategory.AUTHENTICITY,
                      score=90, weight=1.0, status="pass")
    c = CheckResultV2(name="fn", category=DetectorCategory.CAPABILITY,
                      score=50, weight=1.0, status="pass")
    s = calculate_scores([a, c])
    assert s["authenticity_score"] == 90.0
    assert s["capability_score"] == 50.0
    print("  [OK] normal dimension scoring unchanged")


def test_serialize_none_scores_json_safe():
    """_serialize_report 对 None 维度分输出 null（前端 N/A）"""
    from web.app import _serialize_report
    from src.core.models import DetectionReport, Verdict
    report = DetectionReport(
        model="m", protocol=Protocol.ANTHROPIC, mode="standard", degraded=False,
        results=[], total_score=70.0, verdict=Verdict.PASSED,
        authenticity_score=70.0, capability_score=None, compliance_score=None,
        total_tokens=0, total_requests=0, estimated_cost_usd=0.0, has_critical=False,
    )
    import json
    d = _serialize_report(report, Protocol.ANTHROPIC, False, "", "https://x")
    assert d["capability_score"] is None
    json.dumps(d)  # 不抛异常
    print("  [OK] serialize None scores -> JSON null")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("\nAll v3.0.3 budget/envelope tests passed!")
