"""protocol - 协议合规检测（合规）"""

from src.core.detector_base import ActiveDetector
from src.core.models import CheckResultV2, Issue, IssueLevel
from ..config import WEIGHTS, CATEGORIES


class ProtocolDetector(ActiveDetector):
    """协议合规检测：验证响应结构符合 Gemini API 规范"""

    name = "protocol"
    category = CATEGORIES["protocol"]
    weight = WEIGHTS["protocol"]
    modes = ["quick", "standard", "full"]
    timeout = 20

    def run(self, client) -> CheckResultV2:
        resp = client.generate(
            contents=[{"parts": [{"text": "Hi"}]}],
            max_tokens=5,
            detector_name=self.name,
        )

        if not resp.success:
            return CheckResultV2(
                name=self.name, category=self.category, score=0, weight=self.weight,
                status="error", cost_tokens=resp.usage.total_tokens if resp.usage else 0,
                details=f"请求失败: {resp.error}",
            )

        raw = resp.raw_response or {}
        issues = []
        score = 100

        # 检查必需字段
        if "candidates" not in raw:
            score = 20
            issues.append(Issue(level=IssueLevel.CRITICAL, message="响应缺少 candidates 字段", detector_name=self.name))
        else:
            candidates = raw["candidates"]
            if not candidates:
                score = 30
                issues.append(Issue(level=IssueLevel.MAJOR, message="candidates 为空", detector_name=self.name))
            else:
                candidate = candidates[0]
                if "content" not in candidate:
                    score -= 25
                    issues.append(Issue(level=IssueLevel.MAJOR, message="candidate 缺少 content", detector_name=self.name))
                else:
                    content = candidate["content"]
                    if "parts" not in content:
                        score -= 20
                        issues.append(Issue(level=IssueLevel.MAJOR, message="content 缺少 parts", detector_name=self.name))
                    if "role" not in content:
                        score -= 10
                        issues.append(Issue(level=IssueLevel.MINOR, message="content 缺少 role", detector_name=self.name))

                if "finishReason" not in candidate:
                    score -= 10
                    issues.append(Issue(level=IssueLevel.MINOR, message="candidate 缺少 finishReason", detector_name=self.name))

        # 检查 usageMetadata
        if "usageMetadata" not in raw:
            score -= 15
            issues.append(Issue(level=IssueLevel.MAJOR, message="响应缺少 usageMetadata", detector_name=self.name))
        else:
            usage = raw["usageMetadata"]
            for uf in ["promptTokenCount", "candidatesTokenCount", "totalTokenCount"]:
                if uf not in usage:
                    score -= 5
                    issues.append(Issue(level=IssueLevel.MINOR, message=f"usageMetadata 缺少 {uf}", detector_name=self.name))

        score = max(0, score)

        return CheckResultV2(
            name=self.name, category=self.category, score=score, weight=self.weight,
            cost_tokens=resp.usage.total_tokens if resp.usage else 0,
            details=f"协议合规检查完成, score={score}",
            issues=issues,
        )
