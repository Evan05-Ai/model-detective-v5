"""
三维加权评分引擎 + 后端来源推断（v2.1）

评分公式：
  total_score = Σ(detector.score × detector.weight) / Σ(effective_weight)
  仅 skip 不参与分母（v2.4 修复：error 参与评分，score=0）

三维分按 category 分组分别计算：
  authenticity_score = 真伪检测器加权平均
  capability_score   = 能力检测器加权平均
  compliance_score   = 合规检测器加权平均

critical issue → verdict 上限锁定 MARGINAL
verdict: >=85 PASSED_EXCELLENT, 70-84 PASSED, 50-69 MARGINAL, <50 FAILED

v2.4 新增：
  - error 状态参与评分（score=0），防止大量 error 导致总分虚高
  - error 惩罚机制：error 率 ≥ 50% 时额外按比例降低总分

v2.1 新增：
  - BackendSource 推断（根据 identity/message_id/thinking_signature 等结果）
  - 链路类型校准：检测到 Kiro 链路时，某些扣分项降级为提示
"""

from .models import (
    CheckResultV2, DetectionReport, DetectorCategory,
    Issue, IssueLevel, Verdict, Protocol, RunMode, BackendSource,
)
from typing import Optional


# ─── 后端来源推断 ──────────────────────────────────────────────

def infer_backend_source(results: list[CheckResultV2]) -> str:
    """
    根据检测结果推断后端来源。

    优先级：
      1. identity 检测到 Kiro → KIRO_PROXY
      2. identity 检测到 Claude 且有 service_tier → ANTHROPIC_DIRECT (暂无法直接从 results 判断，留待响应头分析)
      3. message_id 格式为 UUID → 疑似 BEDROCK/KIRO
      4. tool_use id 为 tooluse_ → 疑似 BEDROCK/KIRO
      5. 默认 UNKNOWN
    """
    for r in results:
        if r.name == "identity":
            for issue in r.issues:
                if "kiro" in issue.message.lower() or "aws" in issue.message.lower():
                    return BackendSource.KIRO_PROXY.value
                if "bedrock" in issue.message.lower():
                    return BackendSource.BEDROCK_DIRECT.value

    for r in results:
        if r.name == "message_id":
            details_lower = r.details.lower()
            if "uuid" in details_lower:
                return BackendSource.KIRO_PROXY.value  # UUID → 非原生 Anthropic

    for r in results:
        if r.name == "thinking_signature":
            for issue in r.issues:
                if "中转站" in issue.message or "代理" in issue.message:
                    if r.score < 50:
                        return BackendSource.UNKNOWN_PROXY.value
                    return BackendSource.KIRO_PROXY.value

    for r in results:
        if r.name == "identity":
            for issue in r.issues:
                if issue.level in (IssueLevel.OK, IssueLevel.MINOR):
                    return BackendSource.ANTHROPIC_DIRECT.value

    return BackendSource.UNKNOWN.value


# ─── 链路校准 ──────────────────────────────────────────────────

def calibrate_by_backend(results: list[CheckResultV2], backend: str) -> list[CheckResultV2]:
    """
    根据后端来源校准检测结果。

    Kiro 链路的特殊处理：
      - identity 检测到 Kiro → 这是正确识别，不降 authenticity 分
      - thinking_signature 签名缺失 → 降级为 MINOR（预期行为），不判 CRITICAL
    """
    if backend != BackendSource.KIRO_PROXY.value:
        return results

    calibrated = []
    for r in results:
        if r.name == "thinking_signature":
            # Kiro 链路上 signature 缺失是预期的
            new_issues = []
            for issue in r.issues:
                if issue.level == IssueLevel.CRITICAL and "signature" in issue.message.lower():
                    new_issues.append(Issue(
                        level=IssueLevel.MEDIUM,
                        message=f"[Kiro 链路预期行为] {issue.message}。Kiro 链路通常不完整传递 thinking signature。",
                        detector_name=r.name,
                    ))
                else:
                    new_issues.append(issue)
            # v2.4 清理：移除未使用的 has_remaining_critical 变量
            # 在 Kiro 链路上，score 不低于 30（有 thinking 内容就算成功）
            calibrated_score = max(r.score, 30) if not r.status == "error" else r.score
            calibrated.append(CheckResultV2(
                name=r.name, category=r.category, score=calibrated_score,
                weight=r.weight, status=r.status, cost_tokens=r.cost_tokens,
                details=r.details, issues=new_issues,
                raw_response=r.raw_response,
            ))
        else:
            calibrated.append(r)

    return calibrated


# ─── 评分计算 ──────────────────────────────────────────────────

def calculate_scores(results: list[CheckResultV2]) -> dict:
    """
    计算三维评分

    v2.4 修复：增加 error 惩罚机制。当大量检测器 error 时，即使个别
    检测器得分高，总分也应受影响。error 率 >= 50% 时额外惩罚。

    Returns:
        {
            "total_score": float,
            "authenticity_score": float,
            "capability_score": float,
            "compliance_score": float,
            "has_critical": bool,
        }
    """
    has_critical = any(r.has_critical for r in results)

    total = _weighted_avg(results)
    auth = _weighted_avg([r for r in results if r.category == DetectorCategory.AUTHENTICITY])
    cap = _weighted_avg([r for r in results if r.category == DetectorCategory.CAPABILITY])
    comp = _weighted_avg([r for r in results if r.category == DetectorCategory.COMPLIANCE])

    # v2.4 error 惩罚：当 error 检测器比例较高时，额外降低总分
    # 这确保即使个别检测器得分高，大量 error 也会拉低总分
    non_skipped = [r for r in results if r.status != "skip"]
    if non_skipped:
        error_count = sum(1 for r in non_skipped if r.status == "error")
        error_ratio = error_count / len(non_skipped)
        if error_ratio >= 0.5:
            # error 率 >= 50% 时，按比例惩罚
            # 例如 10/11 error → error_ratio=0.91 → penalty=0.91 → total *= (1 - 0.91*0.8) = 0.272
            penalty = error_ratio * 0.8  # 最多惩罚 80%
            total = total * (1.0 - penalty)
            auth = auth * (1.0 - penalty)
            cap = cap * (1.0 - penalty)
            comp = comp * (1.0 - penalty)

    return {
        "total_score": total,
        "authenticity_score": auth,
        "capability_score": cap,
        "compliance_score": comp,
        "has_critical": has_critical,
    }


def _weighted_avg(results: list[CheckResultV2], use_confidence: bool = True) -> float:
    """加权平均，仅 skip 不参与。BUG-11 修复：分数钳制到 0-100

    v2.4 修复：error 状态参与评分（score=0），防止大量 error 导致
    总分虚高。例如 11 个检测器中 10 个 error，只有 1 个 pass(80)，
    旧逻辑只算那个 pass 的 → 80 分，新逻辑算全部 → ~7 分。
    
    v2.6 新增：支持置信度加权评分。当 use_confidence=True 时，
    使用 score * confidence 作为有效分数，降低低置信度检测结果的影响。
    """
    effective = [r for r in results if r.effective]
    if not effective:
        return 0.0

    total_weight = sum(r.weight for r in effective)
    if total_weight == 0:
        return 0.0

    # v2.6: 支持置信度加权
    if use_confidence:
        # 使用加权置信度分数：score * confidence
        # 这样低置信度的检测结果对总分影响更小
        weighted_scores = []
        for r in effective:
            # 钳制分数到 0-100，然后乘以置信度
            clamped_score = max(0.0, min(100.0, r.score))
            effective_score = clamped_score * r.confidence
            weighted_scores.append(effective_score * r.weight)
        
        return sum(weighted_scores) / total_weight
    else:
        # 传统评分方式（向后兼容）
        return sum(max(0.0, min(100.0, r.score)) * r.weight for r in effective) / total_weight


def calculate_confidence_stats(results: list[CheckResultV2]) -> dict:
    """
    v2.6: 计算置信度统计信息
    
    Returns:
        {
            "average_confidence": float,  # 平均置信度
            "min_confidence": float,      # 最低置信度
            "low_confidence_detectors": list,  # 低置信度检测器列表
            "high_confidence_ratio": float,    # 高置信度检测器比例
        }
    """
    effective = [r for r in results if r.effective]
    if not effective:
        return {
            "average_confidence": 0.0,
            "min_confidence": 0.0,
            "low_confidence_detectors": [],
            "high_confidence_ratio": 0.0,
        }
    
    confidences = [r.confidence for r in effective]
    avg_confidence = sum(confidences) / len(confidences)
    min_confidence = min(confidences)
    
    # 低置信度检测器（confidence < 0.5）
    low_confidence = [
        {"name": r.name, "confidence": r.confidence, "reason": r.confidence_reason}
        for r in effective if r.confidence < 0.5
    ]
    
    # 高置信度比例（confidence >= 0.8）
    high_count = sum(1 for c in confidences if c >= 0.8)
    high_ratio = high_count / len(confidences)
    
    return {
        "average_confidence": round(avg_confidence, 2),
        "min_confidence": round(min_confidence, 2),
        "low_confidence_detectors": low_confidence,
        "high_confidence_ratio": round(high_ratio, 2),
    }


def determine_verdict(total_score: float, has_critical: bool) -> Verdict:
    """
    确定最终裁定

    critical issue 时 verdict 上限锁定 MARGINAL
    """
    # critical issue 锁定上限
    if has_critical and total_score >= 70:
        return Verdict.MARGINAL

    if total_score >= 85:
        return Verdict.PASSED_EXCELLENT
    elif total_score >= 70:
        return Verdict.PASSED
    elif total_score >= 50:
        return Verdict.MARGINAL
    else:
        return Verdict.FAILED


def build_report(
    model: str,
    protocol: Protocol,
    mode: str,
    degraded: bool,
    results: list[CheckResultV2],
    total_tokens: int,
    total_requests: int,
    estimated_cost_usd: float,
    duration_seconds: float = 0.0,
    baseline_diff: Optional[dict] = None,
) -> DetectionReport:
    """构建完整检测报告（v2.1 含链路推断和校准）"""
    # 1. 推断后端来源
    backend_source = infer_backend_source(results)

    # 2. 根据后端来源校准结果
    calibrated_results = calibrate_by_backend(results, backend_source)

    # 3. 计算评分
    scores = calculate_scores(calibrated_results)
    verdict = determine_verdict(scores["total_score"], scores["has_critical"])

    return DetectionReport(
        model=model,
        protocol=protocol,
        mode=mode,
        degraded=degraded,
        results=calibrated_results,
        total_score=scores["total_score"],
        verdict=verdict,
        authenticity_score=scores["authenticity_score"],
        capability_score=scores["capability_score"],
        compliance_score=scores["compliance_score"],
        total_tokens=total_tokens,
        total_requests=total_requests,
        estimated_cost_usd=estimated_cost_usd,
        has_critical=scores["has_critical"],
        backend_source=backend_source,
        baseline_diff=baseline_diff,
        duration_seconds=duration_seconds,
    )
