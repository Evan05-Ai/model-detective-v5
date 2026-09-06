#!/usr/bin/env python3
"""v3.0.1 预算口径修复测试：缓存读取不再冲爆检测预算

复现线上 bug：Kiro 类中转站每次响应上报 ~45k cache_read_input_tokens
（上游系统提示走缓存），旧代码按全价计入 Runner 预算 → 2-3 个请求就
"耗尽" 100k 预算，10/13 检测器被跳过（截图证据：已用 239583/100000）。
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.core.detector_base import ActiveDetector
from src.core.models import CheckResultV2, DetectorCategory, RunMode, Protocol
from src.core.runner import Runner
from src.protocols.base_client import TokenUsage
from src.protocols.anthropic.client import AnthropicClient
from src.protocols.openai.client import OpenAIClient


class CountingClient:
    """模拟 Kiro 类中转站客户端：每次请求上报巨额 cache_read"""

    def __init__(self, per_request_total, per_request_budget):
        self.calls = 0
        self._total = 0
        self._budget = 0
        self.per_request_total = per_request_total
        self.per_request_budget = per_request_budget

    def messages(self, **kwargs):
        self.calls += 1
        self._total += self.per_request_total
        self._budget += self.per_request_budget
        from src.protocols.base_client import ProtocolResponse
        return ProtocolResponse(
            success=True, content="ok", model="claude-opus-5", headers={},
            usage=TokenUsage(
                prompt_tokens=200, completion_tokens=50,
                total_tokens=self.per_request_total,
                cache_read_input_tokens=self.per_request_total - 250,
                budget_tokens=self.per_request_budget,
            ),
        )

    def get_budget_tokens(self):
        return self._budget

    def get_cost_summary(self):
        return {"total_tokens": self._total, "budget_tokens": self._budget,
                "total_requests": self.calls, "estimated_cost_usd": 0.01}


class TinyDetector(ActiveDetector):
    """每次运行发 1 个请求的迷你检测器"""
    weight = 0.1
    modes = ["quick", "standard", "full"]
    estimated_tokens = 600

    def __init__(self, name, priority_group=1):
        self.name = name
        self.category = DetectorCategory.AUTHENTICITY

    def run(self, client) -> CheckResultV2:
        client.messages(detector_name=self.name)
        return CheckResultV2(name=self.name, category=self.category,
                             score=90, weight=self.weight, cost_tokens=0)


def _make_runner(client, detectors, budget_mode=RunMode.STANDARD):
    return Runner(
        client=client,
        active_detectors=detectors,
        passive_detectors=[],
        protocol=Protocol.ANTHROPIC,
        model="claude-opus-5",
        mode=budget_mode,
    )


def test_token_usage_budget_fallback():
    """budget_tokens 未设置时回退 total_tokens"""
    u = TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    assert u.effective_budget_tokens == 15
    u2 = TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=100,
                    budget_tokens=15)
    assert u2.effective_budget_tokens == 15
    print("  [OK] TokenUsage budget fallback")


def test_anthropic_record_usage_excludes_cache_read():
    """AnthropicClient 预算计数器剔除 cache_read"""
    c = AnthropicClient("https://example.com", "sk-test-123456", "claude-opus-5")
    # Kiro 类响应：total 45250，其中 cache_read 45000
    c._record_usage(TokenUsage(
        prompt_tokens=200, completion_tokens=50, total_tokens=45250,
        cache_read_input_tokens=45000, budget_tokens=250))
    assert c.get_budget_tokens() == 250
    # 未设置 budget_tokens 的旧式用法回退 total
    c._record_usage(TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15))
    assert c.get_budget_tokens() == 265
    # 展示口径保持上报总量
    assert c.get_cost_summary()["total_tokens"] == 45265
    assert c.get_cost_summary()["budget_tokens"] == 265
    print("  [OK] anthropic budget counter excludes cache_read")


def test_openai_parse_usage_excludes_cached():
    """OpenAI usage 解析：cached_tokens 从预算口径剔除"""
    u = OpenAIClient._parse_usage({
        "prompt_tokens": 1000, "completion_tokens": 50, "total_tokens": 1050,
        "prompt_tokens_details": {"cached_tokens": 900},
    })
    assert u.cached_tokens == 900
    assert u.total_tokens == 1050
    assert u.budget_tokens == 150
    u2 = OpenAIClient._parse_usage({"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15})
    assert u2.budget_tokens == 15
    print("  [OK] openai usage parse excludes cached tokens")


def test_kiro_cache_relay_no_budget_skips():
    """核心回归：cache_read 巨额上报不再导致检测器被预算跳过

    旧代码：detector1 实际 45000 → detector2 后 90000 → detector3 起
    全部 SKIP（截图中的 239583/100000）。
    新代码：预算口径 250/请求 → 4 个检测器全部运行。
    """
    client = CountingClient(per_request_total=45000, per_request_budget=250)
    detectors = [TinyDetector(f"det_{i}") for i in range(4)]
    runner = _make_runner(client, detectors)
    report = runner.run()

    skips = [r for r in report.results if r.status == "skip"]
    assert not skips, f"不应有 SKIP，实际: {[(r.name, r.details) for r in skips]}"
    assert client.calls == 5  # 1 preflight + 4 detectors
    assert report.total_tokens == 5 * 45000  # 展示口径为上报总量
    print("  [OK] kiro cache relay: all detectors ran (no budget skips)")


def test_plain_inflation_blocked_per_detector():
    """无缓存字段的纯虚增上报（120k/请求）：预检后单项预算检查即拦截，
    后续检测器全部 SKIP 且消息含真实用量——钱包保护按预期工作"""
    client = CountingClient(per_request_total=120000, per_request_budget=120000)
    detectors = [TinyDetector("p1_a"), TinyDetector("p1_b")]
    runner = _make_runner(client, detectors)
    report = runner.run()
    by_name = {r.name: r for r in report.results}
    # 预检已用 120k > 预算 100k → 两个检测器都被单项检查拦截
    assert by_name["p1_a"].status == "skip"
    assert "Token 预算耗尽" in by_name["p1_a"].details
    assert "120000" in by_name["p1_a"].details
    # 除预检外不应再发任何请求
    assert client.calls == 1
    print("  [OK] plain inflation blocked at per-detector check")


def test_hard_stop_after_single_detector_overshoot():
    """组级 3 倍费用保护：单检测器内部多次请求累积超 3 倍预算时，
    后续优先级组被止损并给出明确消息"""
    class BurstClient(CountingClient):
        def messages(self, **kwargs):
            # 预检（第一次调用）消耗小，之后每次 90k
            if self.calls == 0:
                self.calls += 1
                self._total += 1000
                self._budget += 1000
                from src.protocols.base_client import ProtocolResponse
                return ProtocolResponse(success=True, content="ok", model="x",
                                        headers={}, usage=TokenUsage(total_tokens=1000))
            return super().messages(**kwargs)

    class IdentityLikeDetector(ActiveDetector):
        name = "identity"
        category = DetectorCategory.AUTHENTICITY
        weight = 0.1
        modes = ["quick", "standard", "full"]
        estimated_tokens = 600

        def run(self, client) -> CheckResultV2:
            for _ in range(4):   # 4 次请求 × 90k = 360k
                client.messages(detector_name=self.name)
            return CheckResultV2(name=self.name, category=self.category,
                                 score=90, weight=self.weight)

    client = BurstClient(per_request_total=90000, per_request_budget=90000)
    runner = _make_runner(client, [IdentityLikeDetector(), TinyDetector("p2_a")])
    from src.core.runner import DETECTOR_PRIORITY
    DETECTOR_PRIORITY["p2_a"] = 2
    try:
        report = runner.run()
    finally:
        DETECTOR_PRIORITY.pop("p2_a", None)

    by_name = {r.name: r for r in report.results}
    # P1 后预算口径 = 1k + 4×90k = 361k > 3×100k → P2 组被止损
    assert by_name["p2_a"].status == "skip"
    assert "费用保护" in by_name["p2_a"].details
    print("  [OK] group-level 3x hard stop fires with clear message")


def test_reservations_released_after_run():
    """检测器完成后预估占用必须清零"""
    client = CountingClient(per_request_total=1000, per_request_budget=1000)
    detectors = [TinyDetector(f"det_{i}") for i in range(3)]
    runner = _make_runner(client, detectors)
    runner.run()
    assert runner._reserved_tokens == 0, "预估占用未释放"
    print("  [OK] reservations released after run")


def test_budget_exhaustion_skip_message():
    """预算真正耗尽时仍有清晰跳过消息（含实际用量）"""
    client = CountingClient(per_request_total=1000, per_request_budget=99000)
    d1 = TinyDetector("big_a")   # preflight 99k + detector 请求 99k → 接近爆
    d2 = TinyDetector("big_b")
    runner = _make_runner(client, [d1, d2])
    report = runner.run()
    statuses = {r.name: r.status for r in report.results}
    # preflight(99k) + big_a 请求(99k) → big_b 检查时 used 已 >= 198k → skip
    assert statuses.get("big_b") == "skip"
    details = next(r.details for r in report.results if r.name == "big_b")
    assert "Token 预算耗尽" in details
    print("  [OK] budget exhaustion skip message present")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("\nAll v3.0.1 budget tests passed!")
