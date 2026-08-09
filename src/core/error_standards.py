"""
错误评分标准规范（v2.6）

统一所有检测器的错误处理和评分标准，确保一致性。

使用方式:
    from src.core.error_standards import ErrorScore, create_error_result
    
    if not resp.success:
        return create_error_result(
            detector=self,
            error_type=ErrorScore.REQUEST_FAILED,
            details=f"请求失败: {resp.error}",
            cost_tokens=resp.usage.total_tokens if resp.usage else 0,
        )
"""

from dataclasses import dataclass
from typing import Optional
from src.core.models import CheckResultV2, Issue, IssueLevel


@dataclass
class ErrorStandard:
    """错误评分标准定义"""
    score: float           # 错误时的得分
    confidence: float      # 错误时的置信度（通常为 0，表示无法判断）
    issue_level: IssueLevel
    default_message: str


class ErrorScore:
    """标准错误评分定义"""
    
    # 请求完全失败（网络错误、认证失败等）
    REQUEST_FAILED = ErrorStandard(
        score=0,
        confidence=0.0,
        issue_level=IssueLevel.MAJOR,
        default_message="检测请求失败",
    )
    
    # 响应格式错误（返回了但格式不对）
    INVALID_RESPONSE = ErrorStandard(
        score=10,
        confidence=0.3,
        issue_level=IssueLevel.CRITICAL,
        default_message="响应格式异常",
    )
    
    # 关键字段缺失
    MISSING_CRITICAL_FIELD = ErrorStandard(
        score=15,
        confidence=0.4,
        issue_level=IssueLevel.CRITICAL,
        default_message="关键响应字段缺失",
    )
    
    # 部分成功但有警告
    PARTIAL_SUCCESS = ErrorStandard(
        score=50,
        confidence=0.6,
        issue_level=IssueLevel.MINOR,
        default_message="部分成功但存在异常",
    )
    
    # 预算耗尽跳过
    BUDGET_EXHAUSTED = ErrorStandard(
        score=0,
        confidence=0.0,
        issue_level=IssueLevel.MINOR,
        default_message="Token 预算耗尽，检测被跳过",
    )


def create_error_result(
    detector,
    error_type: ErrorStandard,
    details: str = "",
    cost_tokens: int = 0,
    custom_message: Optional[str] = None,
) -> CheckResultV2:
    """
    创建标准化的错误检测结果
    
    Args:
        detector: 检测器实例（需有 name, category, weight 属性）
        error_type: 错误类型（ErrorScore 中的常量）
        details: 详细错误信息
        cost_tokens: 消耗的 token 数
        custom_message: 自定义错误消息（可选）
    
    Returns:
        标准化的 CheckResultV2
    """
    return CheckResultV2(
        name=detector.name,
        category=detector.category,
        score=error_type.score,
        weight=detector.weight,
        status="error",
        cost_tokens=cost_tokens,
        confidence=error_type.confidence,
        confidence_reason=f"检测失败: {error_type.default_message}" if not custom_message else f"检测失败: {custom_message}",
        details=details or error_type.default_message,
        issues=[Issue(
            level=error_type.issue_level,
            message=custom_message or error_type.default_message,
            detector_name=detector.name,
        )],
    )


def create_skip_result(
    detector,
    reason: str,
    cost_tokens: int = 0,
) -> CheckResultV2:
    """
    创建标准化的跳过检测结果（预算耗尽等）
    
    Args:
        detector: 检测器实例
        reason: 跳过原因
        cost_tokens: 已消耗的 token 数
    
    Returns:
        标准化的 CheckResultV2，status="skip"
    """
    return CheckResultV2(
        name=detector.name,
        category=detector.category,
        score=0,
        weight=detector.weight,
        status="skip",
        cost_tokens=cost_tokens,
        confidence=0.0,
        confidence_reason=f"检测被跳过: {reason}",
        details=reason,
        issues=[Issue(
            level=IssueLevel.MINOR,
            message=f"检测被跳过: {reason}",
            detector_name=detector.name,
        )],
    )
