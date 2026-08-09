#!/usr/bin/env python3
"""评分引擎测试 - 三维分、critical锁定、verdict阈值"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.core.scorer import calculate_scores, determine_verdict, build_report, infer_backend_source, calibrate_by_backend
from src.core.models import (
    CheckResultV2, DetectorCategory, IssueLevel, Issue,
    Verdict, Protocol, DetectionReport, BackendSource,
)


def test_simple_scoring():
    """基础加权平均"""
    r1 = CheckResultV2(name="a", category=DetectorCategory.AUTHENTICITY, score=90, weight=0.25)
    r2 = CheckResultV2(name="b", category=DetectorCategory.AUTHENTICITY, score=70, weight=0.15)
    s = calculate_scores([r1, r2])
    expected = (90 * 0.25 + 70 * 0.15) / (0.25 + 0.15)
    assert abs(s["total_score"] - expected) < 0.01, f"{s['total_score']} != {expected}"
    assert not s["has_critical"]
    print("  [OK] test_simple_scoring")


def test_skip_not_counted():
    """skip 不参与分母，error 参与（v2.4 修复）"""
    r1 = CheckResultV2(name="a", category=DetectorCategory.AUTHENTICITY, score=90, weight=0.25, status="pass")
    r2 = CheckResultV2(name="b", category=DetectorCategory.AUTHENTICITY, score=0, weight=0.15, status="skip")
    r3 = CheckResultV2(name="c", category=DetectorCategory.AUTHENTICITY, score=0, weight=0.15, status="error")
    s = calculate_scores([r1, r2, r3])
    # skip 不参与，但 error 参与（score=0），所以总分应该被拉低
    # effective = [r1(90, 0.25), r3(0, 0.15)] → (90*0.25 + 0*0.15) / (0.25+0.15) = 56.25
    # error_ratio = 1/2 = 0.5 → penalty = 0.5 * 0.8 = 0.4 → 56.25 * 0.6 = 33.75
    assert s["total_score"] < 90.0, f"error应拉低总分: {s['total_score']}"
    assert s["total_score"] == 33.75, f"总分计算错误: {s['total_score']}"
    print("  [OK] test_skip_not_counted")


def test_error_penalty():
    """v2.4: 大量error时应严重拉低总分"""
    # 模拟 11 个检测器中 10 个 error，只有 1 个 pass(80)
    results = []
    results.append(CheckResultV2(name="integrity", category=DetectorCategory.COMPLIANCE, score=80, weight=0.06, status="pass"))
    for i in range(10):
        results.append(CheckResultV2(name=f"det_{i}", category=DetectorCategory.AUTHENTICITY, score=0, weight=0.094, status="error"))
    s = calculate_scores(results)
    # error_ratio = 10/11 ≈ 0.909, penalty = 0.909 * 0.8 = 0.727
    # raw_score = (80*0.06) / (0.06 + 10*0.094) = 4.8 / 1.0 = 4.8
    # penalty_score = 4.8 * (1 - 0.727) = 4.8 * 0.273 = 1.31
    assert s["total_score"] < 10.0, f"大量error应拉低总分到极低: {s['total_score']}"
    print("  [OK] test_error_penalty")


def test_no_error_penalty_when_all_pass():
    """v2.4: 全部pass时不应有error惩罚"""
    r1 = CheckResultV2(name="a", category=DetectorCategory.AUTHENTICITY, score=90, weight=0.5, status="pass")
    r2 = CheckResultV2(name="b", category=DetectorCategory.AUTHENTICITY, score=80, weight=0.5, status="pass")
    s = calculate_scores([r1, r2])
    expected = (90*0.5 + 80*0.5) / (0.5+0.5)
    assert abs(s["total_score"] - expected) < 0.01, f"全部pass不应有惩罚: {s['total_score']} vs {expected}"
    print("  [OK] test_no_error_penalty_when_all_pass")


def test_empty_scoring():
    """空检测器列表"""
    s = calculate_scores([])
    assert s["total_score"] == 0.0
    assert not s["has_critical"]
    print("  [OK] test_empty_scoring")


def test_authenticity_score():
    """真伪分单独计算"""
    r1 = CheckResultV2(name="a", category=DetectorCategory.AUTHENTICITY, score=90, weight=0.25)
    r2 = CheckResultV2(name="b", category=DetectorCategory.CAPABILITY, score=50, weight=0.20)
    r3 = CheckResultV2(name="c", category=DetectorCategory.COMPLIANCE, score=70, weight=0.10)
    s = calculate_scores([r1, r2, r3])
    assert s["authenticity_score"] == 90.0
    assert s["capability_score"] == 50.0
    assert s["compliance_score"] == 70.0
    print("  [OK] test_authenticity_score")


def test_critical_locks_verdict():
    """critical issue → verdict 上限锁定 MARGINAL"""
    r1 = CheckResultV2(name="a", category=DetectorCategory.AUTHENTICITY, score=95, weight=1.0,
                       issues=[Issue(level=IssueLevel.CRITICAL, message="fail")])
    s = calculate_scores([r1])
    v = determine_verdict(s["total_score"], s["has_critical"])
    assert v == Verdict.MARGINAL, f"95分但critical应锁定为MARGINAL: {v}"
    print("  [OK] test_critical_locks_verdict")


def test_verdict_thresholds():
    """verdict 阈值测试"""
    # >= 85
    v = determine_verdict(85, False)
    assert v == Verdict.PASSED_EXCELLENT
    # 70-84
    v = determine_verdict(70, False)
    assert v == Verdict.PASSED
    # 50-69
    v = determine_verdict(69, False)
    assert v == Verdict.MARGINAL
    v = determine_verdict(50, False)
    assert v == Verdict.MARGINAL
    # < 50
    v = determine_verdict(49, False)
    assert v == Verdict.FAILED
    print("  [OK] test_verdict_thresholds")


def test_build_report():
    """构建完整报告"""
    from src.core.models import RunMode
    r1 = CheckResultV2(name="a", category=DetectorCategory.AUTHENTICITY, score=90, weight=0.25)
    report = build_report(
        model="test-model",
        protocol=Protocol.OPENAI,
        mode="standard",
        degraded=False,
        results=[r1],
        total_tokens=100,
        total_requests=5,
        estimated_cost_usd=0.001,
        duration_seconds=10.0,
    )
    assert isinstance(report, DetectionReport)
    assert report.model == "test-model"
    assert report.total_score == 90.0
    assert report.exit_code == 0
    print("  [OK] test_build_report")


def test_exit_codes():
    """V2 退出码"""
    r1 = CheckResultV2(name="a", category=DetectorCategory.AUTHENTICITY, score=90, weight=1.0)
    r_pass = build_report("m", Protocol.OPENAI, "s", False, [r1], 0, 0, 0)
    assert r_pass.exit_code == 0

    r_fail = CheckResultV2(name="a", category=DetectorCategory.AUTHENTICITY, score=30, weight=1.0)
    r_fail_report = build_report("m", Protocol.OPENAI, "s", False, [r_fail], 0, 0, 0)
    assert r_fail_report.exit_code == 1, f"30分应FAILED退出码1: {r_fail_report.verdict}"

    r_marg = CheckResultV2(name="a", category=DetectorCategory.AUTHENTICITY, score=60, weight=1.0)
    r_marg_report = build_report("m", Protocol.OPENAI, "s", False, [r_marg], 0, 0, 0)
    assert r_marg_report.exit_code == 2, f"60分应MARGINAL退出码2: {r_marg_report.verdict}"
    print("  [OK] test_exit_codes")


def test_infer_backend_source():
    """后端来源推断"""
    # 1. Kiro proxy detected via identity issue
    r_kiro = CheckResultV2(
        name="identity", category=DetectorCategory.AUTHENTICITY, score=80, weight=1.0,
        issues=[Issue(level=IssueLevel.MINOR, message="Detected Kiro proxy", detector_name="identity")],
    )
    assert infer_backend_source([r_kiro]) == BackendSource.KIRO_PROXY.value

    # 2. Bedrock detected via identity issue
    r_bedrock = CheckResultV2(
        name="identity", category=DetectorCategory.AUTHENTICITY, score=80, weight=1.0,
        issues=[Issue(level=IssueLevel.MINOR, message="Detected bedrock backend", detector_name="identity")],
    )
    assert infer_backend_source([r_bedrock]) == BackendSource.BEDROCK_DIRECT.value

    # 3. UUID message_id -> Kiro proxy
    r_uuid = CheckResultV2(
        name="message_id", category=DetectorCategory.AUTHENTICITY, score=70, weight=1.0,
        details="message_id format: uuid",
    )
    assert infer_backend_source([r_uuid]) == BackendSource.KIRO_PROXY.value

    # 4. Anthropic direct: identity with OK issue
    r_direct = CheckResultV2(
        name="identity", category=DetectorCategory.AUTHENTICITY, score=100, weight=1.0,
        issues=[Issue(level=IssueLevel.OK, message="Direct Anthropic API", detector_name="identity")],
    )
    assert infer_backend_source([r_direct]) == BackendSource.ANTHROPIC_DIRECT.value

    # 5. Unknown: no matching signals
    r_empty = CheckResultV2(
        name="basic_request", category=DetectorCategory.AUTHENTICITY, score=90, weight=1.0,
    )
    assert infer_backend_source([r_empty]) == BackendSource.UNKNOWN.value
    print("  [OK] test_infer_backend_source")


def test_calibrate_by_backend():
    """Kiro 链路校准"""
    # thinking_signature with CRITICAL issue on Kiro -> should be downgraded to MEDIUM
    r_sig = CheckResultV2(
        name="thinking_signature", category=DetectorCategory.AUTHENTICITY, score=20, weight=0.25,
        status="pass",
        issues=[Issue(level=IssueLevel.CRITICAL, message="thinking signature missing", detector_name="thinking_signature")],
    )

    # Non-Kiro: no calibration
    calibrated_non_kiro = calibrate_by_backend([r_sig], BackendSource.UNKNOWN.value)
    assert calibrated_non_kiro[0].score == 20, "Non-Kiro should not calibrate"
    assert any(i.level == IssueLevel.CRITICAL for i in calibrated_non_kiro[0].issues)

    # Kiro: CRITICAL downgraded to MEDIUM, score boosted to at least 30
    calibrated_kiro = calibrate_by_backend([r_sig], BackendSource.KIRO_PROXY.value)
    assert calibrated_kiro[0].score >= 30, f"Kiro should boost score to >=30, got {calibrated_kiro[0].score}"
    has_critical = any(i.level == IssueLevel.CRITICAL for i in calibrated_kiro[0].issues)
    assert not has_critical, "Kiro should downgrade CRITICAL to MEDIUM"
    has_medium = any(i.level == IssueLevel.MEDIUM for i in calibrated_kiro[0].issues)
    assert has_medium, "Kiro should have MEDIUM issue"

    # Non-thinking_signature detectors should not be affected
    r_other = CheckResultV2(
        name="identity", category=DetectorCategory.AUTHENTICITY, score=80, weight=0.15,
    )
    calibrated_other = calibrate_by_backend([r_other], BackendSource.KIRO_PROXY.value)
    assert calibrated_other[0].score == 80, "Non-thinking_signature should not be calibrated"
    print("  [OK] test_calibrate_by_backend")


if __name__ == "__main__":
    print("Testing scorer.py...")
    test_simple_scoring()
    test_skip_not_counted()
    test_error_penalty()
    test_no_error_penalty_when_all_pass()
    test_empty_scoring()
    test_authenticity_score()
    test_critical_locks_verdict()
    test_verdict_thresholds()
    test_build_report()
    test_exit_codes()
    test_infer_backend_source()
    test_calibrate_by_backend()
    print("All scorer tests passed!")
