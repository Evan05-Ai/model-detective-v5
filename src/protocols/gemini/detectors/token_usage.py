"""token_usage - Token 计费验证（合规）"""

from src.core.detector_base import ActiveDetector
from src.core.models import CheckResultV2, Issue, IssueLevel
from ..config import WEIGHTS, CATEGORIES


class TokenUsageDetector(ActiveDetector):
    """Token 计费检测：验证 Gemini usageMetadata 字段"""

    name = "token_usage"
    category = CATEGORIES["token_usage"]
    weight = WEIGHTS["token_usage"]
    modes = ["standard", "full"]
    timeout = 15

    def run(self, client) -> CheckResultV2:
        resp = client.generate(
            contents=[{"parts": [{"text": "Write a short poem about the sun."}]}],
            max_tokens=100,
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

        if not usage:
            score = 20
            issues.append(Issue(
                level=IssueLevel.CRITICAL,
                message="usageMetadata 缺失",
                detector_name=self.name,
            ))
        else:
            if usage.prompt_tokens == 0:
                score = 40
                issues.append(Issue(
                    level=IssueLevel.MAJOR,
                    message="promptTokenCount=0，计费异常",
                    detector_name=self.name,
                ))

            if usage.completion_tokens == 0:
                content = resp.content or ""
                if content:
                    score = 30
                    issues.append(Issue(
                        level=IssueLevel.CRITICAL,
                        message="candidatesTokenCount=0 但有响应内容",
                        detector_name=self.name,
                    ))

            # 验证 total = prompt + completion
            if usage.total_tokens != usage.prompt_tokens + usage.completion_tokens:
                score -= 20
                issues.append(Issue(
                    level=IssueLevel.MAJOR,
                    message=f"totalTokenCount ({usage.total_tokens}) != prompt ({usage.prompt_tokens}) + candidates ({usage.completion_tokens})",
                    detector_name=self.name,
                ))

        return CheckResultV2(
            name=self.name, category=self.category, score=score, weight=self.weight,
            cost_tokens=usage.total_tokens if usage else 0,
            details=f"prompt={usage.prompt_tokens if usage else 0}, completion={usage.completion_tokens if usage else 0}, total={usage.total_tokens if usage else 0}",
            issues=issues,
        )
