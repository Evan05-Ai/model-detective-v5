"""protocol - 协议合规检测（合规）"""

from src.core.detector_base import ActiveDetector
from src.core.models import CheckResultV2, Issue, IssueLevel
from ..config import WEIGHTS, CATEGORIES


class ProtocolDetector(ActiveDetector):
    """协议合规检测：验证响应结构符合 OpenAI API 规范"""

    name = "protocol"
    category = CATEGORIES["protocol"]
    weight = WEIGHTS["protocol"]
    modes = ["quick", "standard", "full"]
    timeout = 20

    def run(self, client) -> CheckResultV2:
        resp = client.chat(
            messages=[{"role": "user", "content": "Hi"}],
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
        required_fields = ["id", "object", "created", "model", "choices"]
        for field in required_fields:
            if field not in raw:
                score -= 20
                issues.append(Issue(
                    level=IssueLevel.MAJOR,
                    message=f"响应缺少必需字段: {field}",
                    detector_name=self.name,
                ))

        # 检查 object 字段
        if raw.get("object") != "chat.completion":
            score -= 15
            issues.append(Issue(
                level=IssueLevel.MINOR,
                message=f"object 字段不是 'chat.completion': {raw.get('object')}",
                detector_name=self.name,
            ))

        # 检查 choices 结构
        choices = raw.get("choices", [])
        if choices:
            choice = choices[0]
            if "message" not in choice:
                score -= 20
                issues.append(Issue(level=IssueLevel.MAJOR, message="choice 缺少 message 字段", detector_name=self.name))
            else:
                msg = choice["message"]
                if "role" not in msg:
                    score -= 10
                    issues.append(Issue(level=IssueLevel.MINOR, message="message 缺少 role 字段", detector_name=self.name))
                if "content" not in msg:
                    score -= 10
                    issues.append(Issue(level=IssueLevel.MINOR, message="message 缺少 content 字段", detector_name=self.name))

            if "finish_reason" not in choice:
                score -= 10
                issues.append(Issue(level=IssueLevel.MINOR, message="choice 缺少 finish_reason 字段", detector_name=self.name))

        # 检查 usage 字段
        if "usage" not in raw:
            score -= 15
            issues.append(Issue(level=IssueLevel.MAJOR, message="响应缺少 usage 字段", detector_name=self.name))
        else:
            usage = raw["usage"]
            for uf in ["prompt_tokens", "completion_tokens", "total_tokens"]:
                if uf not in usage:
                    score -= 5
                    issues.append(Issue(level=IssueLevel.MINOR, message=f"usage 缺少 {uf}", detector_name=self.name))

        score = max(0, score)

        return CheckResultV2(
            name=self.name, category=self.category, score=score, weight=self.weight,
            cost_tokens=resp.usage.total_tokens if resp.usage else 0,
            details=f"字段检查完成, score={score}",
            issues=issues,
            raw_response=raw,
        )
