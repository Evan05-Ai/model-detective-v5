#!/usr/bin/env python3
"""Runner 两阶段执行测试"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.core.detector_base import ActiveDetector, PassiveDetector
from src.core.models import CheckResultV2, DetectorCategory, RunMode, Protocol
from src.core.runner import Runner


class MockClient:
    """模拟客户端"""
    def __init__(self):
        self.calls = []

    def chat(self, **kwargs):
        self.calls.append(kwargs.get("detector_name", ""))
        from src.protocols.base_client import ProtocolResponse
        return type("MockResp", (), {
            "success": True,
            "content": "hello",
            "model": "test-model",
            "model_field": "test-model",
            "headers": {},
            "usage": None,
        })()

    def messages(self, **kwargs):
        return self.chat(**kwargs)

    def generate(self, **kwargs):
        return self.chat(**kwargs)

    def get_cost_summary(self):
        return {"total_tokens": 50, "total_requests": 2, "estimated_cost_usd": 0.001}


class MockActive(ActiveDetector):
    name = "mock_active"
    category = DetectorCategory.AUTHENTICITY
    weight = 0.5
    modes = ["quick", "standard", "full"]
    timeout = 15

    def run(self, client) -> CheckResultV2:
        return CheckResultV2(name=self.name, category=self.category, score=90, weight=self.weight)


class MockPassive(PassiveDetector):
    name = "mock_passive"
    category = DetectorCategory.COMPLIANCE
    weight = 0.3
    modes = ["standard", "full"]

    def finalize(self) -> CheckResultV2:
        observed = len(self._observations)
        return CheckResultV2(
            name=self.name, category=self.category, score=min(100, observed * 50),
            weight=self.weight,
            details=f"observed {observed} requests",
        )


class SlowMockActive(ActiveDetector):
    """模拟耗时检测器"""
    name = "slow_active"
    category = DetectorCategory.AUTHENTICITY
    weight = 0.2
    modes = ["standard", "full"]
    timeout = 5

    def run(self, client) -> CheckResultV2:
        import time
        time.sleep(0.1)
        return CheckResultV2(name=self.name, category=self.category, score=80, weight=self.weight)


def test_runner_basic():
    """Runner 基础执行"""
    client = MockClient()
    active = [MockActive()]
    passive = [MockPassive()]

    runner = Runner(client, active, passive, Protocol.OPENAI, "test-model", RunMode.STANDARD)
    report = runner.run()

    assert report.model == "test-model"
    assert report.protocol == Protocol.OPENAI
    assert report.total_requests >= 0
    assert report.duration_seconds > 0
    assert len(report.results) >= 2  # active + passive
    print("  [OK] test_runner_basic")


def test_runner_mode_filtering():
    """模式过滤：quick 模式不应运行 standard 检测器"""
    client = MockClient()
    active_quick = MockActive()
    active_quick.name = "quick_only"
    active_quick.modes = ["quick"]

    active_standard = MockActive()
    active_standard.name = "standard_only"
    active_standard.modes = ["standard"]

    runner = Runner(client, [active_quick, active_standard], [], Protocol.OPENAI, "m", RunMode.QUICK)
    report = runner.run()

    names = [r.name for r in report.results]
    assert "quick_only" in names, "quick 模式应运行 quick_only"
    assert "standard_only" not in names, "quick 模式不应运行 standard_only"
    print("  [OK] test_runner_mode_filtering")


def test_passive_observations():
    """PassiveDetector 应观察到 ActiveDetector 的请求"""
    client = MockClient()
    passive = MockPassive()

    runner = Runner(client, [MockActive()], [passive], Protocol.OPENAI, "m", RunMode.STANDARD)
    report = runner.run()

    passive_result = [r for r in report.results if r.name == "mock_passive"]
    assert len(passive_result) == 1
    assert "observed" in passive_result[0].details
    print("  [OK] test_passive_observations")


def test_parallel_execution():
    """并行执行速度应快于串行（至少有并行效果）"""
    import time
    client = MockClient()
    active = [SlowMockActive() for _ in range(3)]

    runner = Runner(client, active, [], Protocol.OPENAI, "m", RunMode.STANDARD, max_workers=4)
    start = time.time()
    report = runner.run()
    duration = time.time() - start

    assert duration < 0.3, f"并行3个0.1s任务应快于串行0.3s: {duration:.3f}s"
    assert len([r for r in report.results if r.status == "pass"]) == 3
    print("  [OK] test_parallel_execution")


if __name__ == "__main__":
    print("Testing runner.py...")
    test_runner_basic()
    test_runner_mode_filtering()
    test_passive_observations()
    test_parallel_execution()
    print("All runner tests passed!")
