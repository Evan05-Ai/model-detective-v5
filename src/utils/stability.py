"""
稳定性评估 - 多次请求延迟/成功率统计

借鉴 hvoy.ai 的稳定性评估维度
"""

import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class StabilityResult:
    """稳定性测试结果"""
    total_requests: int = 0
    success_count: int = 0
    failure_count: int = 0
    latencies: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.success_count / self.total_requests

    @property
    def avg_latency(self) -> float:
        if not self.latencies:
            return 0.0
        return sum(self.latencies) / len(self.latencies)

    @property
    def p50_latency(self) -> float:
        if not self.latencies:
            return 0.0
        sorted_lat = sorted(self.latencies)
        return sorted_lat[len(sorted_lat) // 2]

    @property
    def p95_latency(self) -> float:
        if not self.latencies:
            return 0.0
        sorted_lat = sorted(self.latencies)
        idx = int(len(sorted_lat) * 0.95)
        return sorted_lat[min(idx, len(sorted_lat) - 1)]

    @property
    def cv(self) -> float:
        """变异系数 CV = std/mean"""
        if len(self.latencies) < 2:
            return 0.0
        mean = self.avg_latency
        if mean == 0:
            return 0.0
        variance = sum((x - mean) ** 2 for x in self.latencies) / len(self.latencies)
        return (variance ** 0.5) / mean


def test_stability(client, num_requests: int = 5) -> StabilityResult:
    """
    测试中转站稳定性

    Args:
        client: 协议客户端
        num_requests: 测试请求数

    Returns:
        StabilityResult
    """
    result = StabilityResult()

    for i in range(num_requests):
        start = time.time()

        try:
            # 根据客户端类型调用不同方法
            if hasattr(client, "messages"):
                resp = client.messages(
                    messages=[{"role": "user", "content": f"Say {i}"}],
                    max_tokens=5,
                    detector_name="stability",
                )
            elif hasattr(client, "generate"):
                resp = client.generate(
                    contents=[{"parts": [{"text": f"Say {i}"}]}],
                    max_tokens=5,
                    detector_name="stability",
                )
            else:
                resp = client.chat(
                    messages=[{"role": "user", "content": f"Say {i}"}],
                    max_tokens=5,
                    detector_name="stability",
                )

            latency = time.time() - start
            result.latencies.append(latency)
            result.total_requests += 1

            if resp.success:
                result.success_count += 1
            else:
                result.failure_count += 1
                result.errors.append(resp.error or "unknown")

        except Exception as e:
            latency = time.time() - start
            result.latencies.append(latency)
            result.total_requests += 1
            result.failure_count += 1
            result.errors.append(str(e))

    return result


def format_stability_report(result: StabilityResult) -> str:
    """格式化稳定性报告"""
    lines = [
        f"成功率: {result.success_rate:.0%} ({result.success_count}/{result.total_requests})",
        f"平均延迟: {result.avg_latency:.2f}s",
        f"P50 延迟: {result.p50_latency:.2f}s",
        f"P95 延迟: {result.p95_latency:.2f}s",
        f"延迟变异系数: {result.cv:.2f}",
    ]

    if result.cv > 0.5:
        lines.append("[!] 延迟波动大，稳定性差")
    elif result.cv > 0.3:
        lines.append("[!] 延迟有一定波动")
    else:
        lines.append("[OK] 延迟稳定")

    if result.success_rate < 0.8:
        lines.append("[!] 成功率低，服务不稳定")
    elif result.success_rate < 1.0:
        lines.append("[!] 偶有失败")
    else:
        lines.append("[OK] 全部成功")

    return "\n".join(lines)
