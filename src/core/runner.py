"""
两阶段并行调度器（v2.7 渐进式探测版）

v2.7 变更（渐进式探测机制）：
  - 预检探针（Pre-flight Probe）：正式检测前发送最小请求验证 API 连通性
  - 分优先级执行（Priority Phases）：检测器按优先级分批执行
    * Priority 1（核心真伪）：identity, basic_request, thinking_signature, protocol
    * Priority 2（重要检测）：consistency, model_consistency, behavioral_signature, knowledge, integrity
    * Priority 3（补充检测）：function_calling, structured_output, pdf, long_context, billing 等
  - 早终止机制（Early Termination）：
    * Phase 1 完成后若检测到 CRITICAL issue 且预算剩余 < 30%，跳过 Priority 3
    * Phase 2 完成后若检测到 CRITICAL issue 且预算剩余 < 20%，跳过 Priority 3
  - 节省 Token，避免无效探测

阶段一：所有 ActiveDetector 按优先级分批并行执行（ThreadPoolExecutor）
        请求/响应通过 queue.Queue 推送给 PassiveDetector
阶段二：所有 ActiveDetector 完成后（shutdown wait），串行调用 PassiveDetector.finalize()

BUG-1 修复：预算预分配制，防止并行检测器竞态突破
BUG-4 修复：PassiveDetector 异常结果包含 issues 列表
BUG-5 修复：_ObservableClient 增加截断上限 + 修正 model 字段名
BUG-6 修复：向检测器注入 budget_limit，支持逐探针预算检查
BUG-12 修复：_ObservableClient 缓存包装函数，避免重复创建
"""

import json
import time
import queue
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from .models import CheckResultV2, RunMode, IssueLevel, Issue, Protocol
from .detector_base import ActiveDetector, PassiveDetector
from .modes import get_token_budget, should_run_detector
from .scorer import build_report


# ============================================================
# v2.7: 检测器优先级映射
# ============================================================

DETECTOR_PRIORITY: dict[str, int] = {
    # Priority 1: 核心真伪检测（先执行，结果决定是否继续深入）
    "identity": 1,
    "basic_request": 1,
    "thinking_signature": 1,
    "protocol": 1,

    # Priority 2: 重要检测（紧接核心检测）
    "consistency": 2,
    "model_consistency": 2,
    "behavioral_signature": 2,
    "knowledge": 2,
    "integrity": 2,
    "model_info": 2,

    # Priority 3: 补充检测（可跳过）
    "function_calling": 3,
    "structured_output": 3,
    "pdf": 3,
    "long_context": 3,
    "billing_integrity": 3,
    "message_id": 3,
    "token_usage": 3,
    "token_billing": 3,
}

DEFAULT_PRIORITY = 2

# 早终止预算阈值
EARLY_TERMINAL_BUDGET_THRESHOLD = 0.30  # 预算剩余 < 30% 时触发早终止


class Runner:
    """两阶段并行调度器（v2.7 渐进式探测版）"""

    def __init__(
        self,
        client,
        active_detectors: list[ActiveDetector],
        passive_detectors: list[PassiveDetector],
        protocol: Protocol,
        model: str,
        mode: RunMode,
        degraded: bool = False,
        max_workers: int = 4,
    ):
        self.client = client
        self.active_detectors = active_detectors
        self.passive_detectors = passive_detectors
        self.protocol = protocol
        self.model = model
        self.mode = mode
        self.degraded = degraded
        self.max_workers = max_workers
        self._observe_queue: queue.Queue = queue.Queue()
        self._token_budget = get_token_budget(mode)
        self._tokens_used = 0
        self._budget_lock = threading.Lock()

    def run(self) -> "DetectionReport":
        """执行两阶段检测（v2.7 渐进式版）"""
        start_time = time.time()

        # 过滤当前模式下的检测器
        active = [d for d in self.active_detectors if should_run_detector(d.modes, self.mode)]
        passive = [d for d in self.passive_detectors if should_run_detector(d.modes, self.mode)]

        results: list[CheckResultV2] = []

        # === v2.7: Phase 0 - 预检探针 ===
        probe_result = self._preflight_probe()
        if probe_result is not None:
            results.append(probe_result)
            if probe_result.status == "error":
                # 预检失败，跳过所有检测器
                results.extend(self._skip_all_detectors(active, "预检探针失败，API 不可用"))
                # 仍然运行 passive detectors（观察预检请求）
                self._distribute_observations(passive, results)
                return self._build_final_report(results, passive, start_time)

        # === v2.7: 分优先级执行 ===
        priority_groups = self._group_by_priority(active)

        for priority in sorted(priority_groups.keys()):
            detectors = priority_groups[priority]

            # v2.7: 早终止检查（Phase 1 之后）
            if priority > 1:
                has_critical = any(r.has_critical for r in results)
                budget_remaining_pct = self._budget_remaining_pct()

                if has_critical and budget_remaining_pct < EARLY_TERMINAL_BUDGET_THRESHOLD:
                    # 跳过此优先级组
                    results.extend(self._skip_detectors(
                        detectors,
                        f"早终止：检测到 CRITICAL issue 且预算剩余仅 {budget_remaining_pct:.0%}"
                    ))
                    continue

            # 执行此优先级组
            phase_results = self._run_priority_group(detectors)
            results.extend(phase_results)

            # 分发观察数据
            self._distribute_observations(passive, [])

        # === 阶段二：PassiveDetector 串行 finalize ===
        for pd in passive:
            try:
                result = pd.finalize()
                results.append(result)
            except Exception as e:
                results.append(CheckResultV2(
                    name=pd.name,
                    category=pd.category,
                    score=0,
                    weight=pd.weight,
                    status="error",
                    details=f"被动检测器异常: {e}",
                    issues=[Issue(
                        level=IssueLevel.MAJOR,
                        message=f"{pd.name} finalize 异常: {e}",
                        detector_name=pd.name,
                    )],
                ))

        return self._build_final_report(results, passive, start_time)

    # ============================================================
    # v2.7: 预检探针
    # ============================================================

    def _preflight_probe(self) -> Optional[CheckResultV2]:
        """发送最小探针请求，验证 API 连通性

        Returns:
            None: 探针成功，继续检测
            CheckResultV2: 探针失败，包含错误结果
        """
        try:
            if self.protocol == Protocol.ANTHROPIC:
                resp = self.client.messages(
                    messages=[{"role": "user", "content": "Hi"}],
                    max_tokens=5,
                    detector_name="preflight",
                )
            elif self.protocol == Protocol.OPENAI:
                resp = self.client.chat(
                    messages=[{"role": "user", "content": "Hi"}],
                    max_tokens=5,
                    detector_name="preflight",
                )
            elif self.protocol == Protocol.GEMINI:
                resp = self.client.generate(
                    contents=[{"parts": [{"text": "Hi"}]}],
                    max_tokens=5,
                    detector_name="preflight",
                )
            else:
                return None  # 未知协议，跳过预检

            if resp.success:
                # 预检成功，记录 token 消耗
                if resp.usage:
                    with self._budget_lock:
                        self._tokens_used += resp.usage.total_tokens
                return None
            else:
                # 预检失败
                return CheckResultV2(
                    name="preflight",
                    category=self.active_detectors[0].category if self.active_detectors else "",
                    score=0,
                    weight=0,
                    status="error",
                    cost_tokens=resp.usage.total_tokens if resp.usage else 0,
                    confidence=0.0,
                    confidence_reason="预检探针失败，API 不可用",
                    details=f"预检探针失败: {resp.error}",
                    issues=[Issue(
                        level=IssueLevel.CRITICAL,
                        message=f"API 连通性验证失败: {resp.error}",
                        detector_name="preflight",
                    )],
                )
        except Exception as e:
            return CheckResultV2(
                name="preflight",
                category=self.active_detectors[0].category if self.active_detectors else "",
                score=0,
                weight=0,
                status="error",
                details=f"预检探针异常: {e}",
                issues=[Issue(
                    level=IssueLevel.CRITICAL,
                    message=f"API 连通性验证异常: {e}",
                    detector_name="preflight",
                )],
            )

    # ============================================================
    # v2.7: 优先级分组 & 分批执行
    # ============================================================

    def _group_by_priority(self, detectors: list[ActiveDetector]) -> dict[int, list[ActiveDetector]]:
        """按优先级分组检测器"""
        groups: dict[int, list[ActiveDetector]] = {}
        for d in detectors:
            priority = DETECTOR_PRIORITY.get(d.name, DEFAULT_PRIORITY)
            groups.setdefault(priority, []).append(d)
        return groups

    def _run_priority_group(self, detectors: list[ActiveDetector]) -> list[CheckResultV2]:
        """执行一个优先级组的所有检测器（并行）"""
        results: list[CheckResultV2] = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_detector = {
                executor.submit(self._run_active, detector): detector
                for detector in detectors
            }

            for future in as_completed(future_to_detector):
                detector = future_to_detector[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    results.append(CheckResultV2(
                        name=detector.name,
                        category=detector.category,
                        score=0,
                        weight=detector.weight,
                        status="error",
                        details=f"检测器执行异常: {e}",
                        issues=[Issue(
                            level=IssueLevel.MAJOR,
                            message=f"{detector.name} 执行异常: {e}",
                            detector_name=detector.name,
                        )],
                    ))

        return results

    # ============================================================
    # v2.7: 辅助方法
    # ============================================================

    def _budget_remaining_pct(self) -> float:
        """计算预算剩余百分比"""
        if self._token_budget <= 0:
            return 0.0
        return max(0.0, (self._token_budget - self._tokens_used) / self._token_budget)

    def _skip_detectors(self, detectors: list[ActiveDetector], reason: str) -> list[CheckResultV2]:
        """生成跳过的检测结果"""
        return [
            CheckResultV2(
                name=d.name,
                category=d.category,
                score=0,
                weight=d.weight,
                status="skip",
                details=f"跳过: {reason}",
            )
            for d in detectors
        ]

    def _skip_all_detectors(self, detectors: list[ActiveDetector], reason: str) -> list[CheckResultV2]:
        """跳过所有检测器（预检失败时使用）"""
        return self._skip_detectors(detectors, reason)

    def _distribute_observations(self, passive: list[PassiveDetector], _results: list) -> None:
        """将观察队列数据分发给 PassiveDetector"""
        while not self._observe_queue.empty():
            req, resp, det_name = self._observe_queue.get_nowait()
            for pd in passive:
                pd.observe(req, resp, det_name)

    def _build_final_report(
        self, results: list[CheckResultV2], passive: list[PassiveDetector], start_time: float
    ) -> "DetectionReport":
        """构建最终报告"""
        duration = time.time() - start_time
        cost_summary = self.client.get_cost_summary()

        return build_report(
            model=self.model,
            protocol=self.protocol,
            mode=self.mode.value,
            degraded=self.degraded,
            results=results,
            total_tokens=cost_summary.get("total_tokens", 0),
            total_requests=cost_summary.get("total_requests", 0),
            estimated_cost_usd=cost_summary.get("estimated_cost_usd", 0.0),
            duration_seconds=duration,
        )

    # ============================================================
    # 单检测器执行（线程安全，预算预分配）- 保持原有逻辑
    # ============================================================

    def _run_active(self, detector: ActiveDetector) -> CheckResultV2:
        """执行单个 ActiveDetector（线程安全，预算预分配）

        预算追踪全部在本方法内完成：预扣 -> 执行 -> 修正为实际消耗。
        """
        with self._budget_lock:
            if self._tokens_used + detector.estimated_tokens > self._token_budget:
                return CheckResultV2(
                    name=detector.name,
                    category=detector.category,
                    score=0,
                    weight=detector.weight,
                    status="skip",
                    details=f"Token 预算耗尽（已用 {self._tokens_used}/{self._token_budget}），跳过检测。",
                )
            # 预扣 estimated_tokens
            self._tokens_used += detector.estimated_tokens
            remaining = self._token_budget - self._tokens_used

        # 注入当前剩余预算
        detector.budget_limit = max(0, remaining)

        # 包装 client 以捕获请求/响应
        wrapped_client = _ObservableClient(self.client, self._observe_queue, detector.name)

        try:
            result = detector.run(wrapped_client)
        except Exception as e:
            with self._budget_lock:
                self._tokens_used -= detector.estimated_tokens
            return CheckResultV2(
                name=detector.name,
                category=detector.category,
                score=0,
                weight=detector.weight,
                status="error",
                details=f"执行异常: {e}",
            )

        # 正常完成：退回预扣，计入实际消耗
        with self._budget_lock:
            self._tokens_used -= detector.estimated_tokens
            self._tokens_used += result.cost_tokens

        return result


class _ObservableClient:
    """
    包装协议客户端，拦截请求/响应推入观察队列
    使 PassiveDetector 能观察到其他检测器的请求/响应

    BUG-12 修复：缓存包装函数，避免每次属性访问都创建新函数
    BUG-5 修复：使用 JSON 序列化增加参数上限到 2000 字符
    """

    def __init__(self, client, observe_queue: queue.Queue, detector_name: str):
        self._client = client
        self._queue = observe_queue
        self._detector_name = detector_name
        self._wrapper_cache: dict = {}

    def __getattr__(self, name):
        if name in self._wrapper_cache:
            return self._wrapper_cache[name]

        attr = getattr(self._client, name)

        if callable(attr):
            def wrapper(*args, **kwargs):
                result = attr(*args, **kwargs)
                if not hasattr(result, "success"):
                    return result
                try:
                    req_data = {
                        "method": name,
                        "args": json.dumps(args, default=str, ensure_ascii=False)[:2000],
                        "kwargs": json.dumps(kwargs, default=str, ensure_ascii=False)[:2000],
                    }
                    resp_data = {}
                    if hasattr(result, "success"):
                        resp_data["success"] = result.success
                    if hasattr(result, "content"):
                        resp_data["content"] = (result.content or "")[:500]
                    if hasattr(result, "model"):
                        resp_data["model"] = result.model
                    if hasattr(result, "headers"):
                        resp_data["headers"] = dict(list(result.headers.items())[:10]) if result.headers else {}
                    if hasattr(result, "raw_response"):
                        resp_data["raw"] = result.raw_response
                    self._queue.put((req_data, resp_data, self._detector_name))
                except Exception:
                    pass
                return result
            self._wrapper_cache[name] = wrapper
            return wrapper

        return attr
