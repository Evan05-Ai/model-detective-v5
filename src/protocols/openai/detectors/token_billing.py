"""token_billing - Token 计费验证（合规）"""

from src.core.detector_base import ActiveDetector
from src.core.models import CheckResultV2, Issue, IssueLevel
from ..config import WEIGHTS, CATEGORIES
from src.utils.token_counter import count_tokens


class TokenBillingDetector(ActiveDetector):
    """Token 计费检测：验证 usage 字段是否合理，流式与非流式 token 比对"""

    name = "token_billing"
    category = CATEGORIES["token_billing"]
    weight = WEIGHTS["token_billing"]
    modes = ["standard", "full"]
    timeout = 15
    estimated_tokens = 1500  # v2.5: 设置合理预估，实际消耗约 1000-1500 tokens

    def run(self, client) -> CheckResultV2:
        # 非流式请求
        resp = client.chat(
            messages=[{"role": "user", "content": "Write a haiku about the sea."}],
            max_tokens=50,
            detector_name=self.name,
        )

        if not resp.success:
            return CheckResultV2(
                name=self.name, category=self.category, score=0, weight=self.weight,
                status="error", cost_tokens=0,
                details=f"请求失败: {resp.error}",
            )

        usage = resp.usage
        issues = []
        score = 100

        if not usage or usage.total_tokens == 0:
            score = 30
            issues.append(Issue(
                level=IssueLevel.CRITICAL,
                message="usage 字段为空或 total_tokens=0，可能虚报计费",
                detector_name=self.name,
            ))
        else:
            # 验证 token 数合理性（使用与 billing_integrity 相同的 tiktoken 估算）
            content = resp.content or ""
            estimated_output_tokens = count_tokens(content)
            actual_output = usage.completion_tokens

            if actual_output == 0:
                score = 40
                issues.append(Issue(
                    level=IssueLevel.MAJOR,
                    message="completion_tokens=0 但有响应内容",
                    detector_name=self.name,
                ))
            elif actual_output < estimated_output_tokens * 0.3:
                # 实际 token 远少于估算，可能虚报
                score = 50
                issues.append(Issue(
                    level=IssueLevel.MAJOR,
                    message=f"completion_tokens ({actual_output}) 远少于估算 ({estimated_output_tokens})，可能虚报",
                    detector_name=self.name,
                ))
            elif actual_output > estimated_output_tokens * 5:
                # 实际 token 远多于估算，可能多收费
                score = 60
                issues.append(Issue(
                    level=IssueLevel.MINOR,
                    message=f"completion_tokens ({actual_output}) 远多于估算 ({estimated_output_tokens})",
                    detector_name=self.name,
                ))
            else:
                score = 90

            # 验证 total = prompt + completion
            if usage.total_tokens != usage.prompt_tokens + usage.completion_tokens:
                score -= 20
                issues.append(Issue(
                    level=IssueLevel.MAJOR,
                    message=f"total_tokens ({usage.total_tokens}) != prompt ({usage.prompt_tokens}) + completion ({usage.completion_tokens})",
                    detector_name=self.name,
                ))

        return CheckResultV2(
            name=self.name, category=self.category, score=score, weight=self.weight,
            cost_tokens=usage.total_tokens if usage else 0,
            details=f"prompt={usage.prompt_tokens if usage else 0}, completion={usage.completion_tokens if usage else 0}, total={usage.total_tokens if usage else 0}",
            issues=issues,
        )
