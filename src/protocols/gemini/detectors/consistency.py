"""consistency - 多次响应稳定性检测（真伪，v2.7 重构版）

v2.7 变更（同步 Anthropic consistency v2.7）：
  - 问题改为创意写作（haiku），避免数学问题的"确定性陷阱"
  - 多维度加权评分：答案一致性40% + 特征稳定性30% + 语义相似度30%
  - 渐进式评分，消除二元化跳跃
  - max_tokens=60，3次请求，Token预算=600
  - 评分逻辑共享 src.utils.consistency_scorer
"""

from src.core.detector_base import ActiveDetector
from src.core.models import CheckResultV2
from src.core.error_standards import create_error_result, ErrorScore
from src.utils.consistency_scorer import (
    HAIKU_QUESTION,
    score_responses,
    calc_confidence,
    generate_issues,
)
from ..config import WEIGHTS, CATEGORIES


class ConsistencyDetector(ActiveDetector):
    """一致性检测：多次相同请求验证响应稳定性（v2.7 多维度加权版）

    v2.7 核心改进：
    1. 使用创意写作问题（haiku），避免数学问题的确定性陷阱
    2. 三维度加权评分，消除二元化跳跃
    3. 渐进式评分，更细致地反映一致性程度
    """

    name = "consistency"
    category = CATEGORIES["consistency"]
    weight = WEIGHTS["consistency"]
    modes = ["standard", "full"]
    timeout = 45
    estimated_tokens = 600  # v2.7: 3 次请求 × ~200 tokens

    # v2.7: 创意写作问题
    QUESTION = HAIKU_QUESTION

    def run(self, client) -> CheckResultV2:
        responses: list[str] = []
        total_tokens = 0
        errors: list[str] = []

        # v2.7: 3 次相同请求，temperature=0
        for i in range(3):
            resp = client.generate(
                contents=[{"parts": [{"text": self.QUESTION}]}],
                max_tokens=60,
                temperature=0.0,
                detector_name=self.name,
            )
            if resp.success:
                responses.append((resp.content or "").strip())
                if resp.usage:
                    total_tokens += resp.usage.total_tokens
            else:
                errors.append(f"第{i+1}次请求失败: {resp.error}")

        # 错误处理
        if len(responses) < 2:
            return create_error_result(
                detector=self,
                error_type=ErrorScore.REQUEST_FAILED,
                details=f"请求失败: {'; '.join(errors)}",
                cost_tokens=total_tokens,
                custom_message=f"一致性检测请求失败: {'; '.join(errors[:2])}",
            )

        # === v2.7: 三维度加权评分 ===
        final_score, c_score, f_score, s_score = score_responses(responses)

        # 置信度
        confidence, confidence_reason = calc_confidence(responses, final_score)

        # Issues
        issues = generate_issues(
            responses, c_score, f_score, s_score, self.name
        )

        # 状态判定
        status = "pass" if final_score >= 50 else "fail"

        details = (
            f"3次请求 | "
            f"答案一致性={c_score:.0f}(40%) "
            f"特征稳定性={f_score:.0f}(30%) "
            f"语义相似度={s_score:.0f}(30%) "
            f"=> 加权总分={final_score}"
        )

        return CheckResultV2(
            name=self.name,
            category=self.category,
            score=final_score,
            weight=self.weight,
            status=status,
            cost_tokens=total_tokens,
            confidence=confidence,
            confidence_reason=confidence_reason,
            details=details,
            issues=issues,
        )
