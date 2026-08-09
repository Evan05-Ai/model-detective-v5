"""token_usage - Token 计费验证（合规）"""

from src.core.detector_base import ActiveDetector
from src.core.models import CheckResultV2, Issue, IssueLevel
from ..config import WEIGHTS, CATEGORIES
from src.utils.token_counter import count_tokens


class TokenUsageDetector(ActiveDetector):
    """Token 计费检测：验证 Anthropic usage 字段（input_tokens/output_tokens）"""

    name = "token_usage"
    category = CATEGORIES["token_usage"]
    weight = WEIGHTS["token_usage"]
    modes = ["standard", "full"]
    timeout = 15
    estimated_tokens = 200  # v2.5: prompt ~30 tokens + output ~100 tokens + overhead

    def run(self, client) -> CheckResultV2:
        resp = client.messages(
            messages=[{"role": "user", "content": "Write a short poem about the moon."}],
            max_tokens=100,
            detector_name=self.name,
        )

        if not resp.success:
            return CheckResultV2(
                name=self.name, category=self.category, score=0, weight=self.weight,
                status="error", cost_tokens=0,
                confidence=0.0,
                confidence_reason="Token 计费检测请求失败",
                details=f"请求失败: {resp.error}",
                issues=[Issue(
                    level=IssueLevel.MAJOR,
                    message=f"Token 计费检测请求失败: {resp.error}",
                    detector_name=self.name,
                )],
            )

        usage = resp.usage
        issues = []
        score = 100

        if not usage:
            score = 20
            issues.append(Issue(
                level=IssueLevel.CRITICAL,
                message="usage 字段缺失",
                detector_name=self.name,
            ))
        else:
            # Anthropic 使用 input_tokens / output_tokens
            if usage.prompt_tokens == 0:
                score = 40
                issues.append(Issue(
                    level=IssueLevel.MAJOR,
                    message="input_tokens=0，计费异常",
                    detector_name=self.name,
                ))

            if usage.completion_tokens == 0:
                content = resp.content or ""
                if content:
                    score = 30
                    issues.append(Issue(
                        level=IssueLevel.CRITICAL,
                        message="output_tokens=0 但有响应内容，可能虚报计费",
                        detector_name=self.name,
                    ))

            # 验证 token 数合理性（使用与 billing_integrity 相同的 tiktoken 估算）
            content = resp.content or ""
            estimated_output = count_tokens(content)
            actual_output = usage.completion_tokens

            if actual_output > 0 and actual_output < estimated_output * 0.3:
                score = min(score, 50)
                issues.append(Issue(
                    level=IssueLevel.MAJOR,
                    message=f"output_tokens ({actual_output}) 远少于估算 ({estimated_output})",
                    detector_name=self.name,
                ))

        # v2.6: 根据 usage 完整性确定置信度
        if usage and usage.prompt_tokens > 0 and usage.completion_tokens > 0:
            confidence = 0.9
            confidence_reason = "Token 计费数据完整，输入输出 token 均有记录"
        elif usage:
            confidence = 0.7
            confidence_reason = "Token 计费数据部分缺失或异常"
        else:
            confidence = 0.0
            confidence_reason = "Token 计费数据完全缺失"

        return CheckResultV2(
            name=self.name, category=self.category, score=score, weight=self.weight,
            cost_tokens=usage.total_tokens if usage else 0,
            confidence=confidence,
            confidence_reason=confidence_reason,
            details=f"input={usage.prompt_tokens if usage else 0}, output={usage.completion_tokens if usage else 0}",
            issues=issues,
        )
