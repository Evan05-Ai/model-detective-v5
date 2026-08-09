"""structured_output - 结构化输出检测（能力）"""

import json
from src.core.detector_base import ActiveDetector
from src.core.models import CheckResultV2, Issue, IssueLevel
from ..config import WEIGHTS, CATEGORIES


PERSON_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "age": {"type": "integer"},
        "city": {"type": "string"},
    },
    "required": ["name", "age", "city"],
}


class StructuredOutputDetector(ActiveDetector):
    """结构化输出检测：验证 Gemini responseSchema 模式"""

    name = "structured_output"
    category = CATEGORIES["structured_output"]
    weight = WEIGHTS["structured_output"]
    modes = ["standard", "full"]
    timeout = 30

    def run(self, client) -> CheckResultV2:
        resp = client.generate(
            contents=[{"parts": [{"text": "Generate a random person profile with name, age, and city."}]}],
            max_tokens=100,
            response_schema=PERSON_SCHEMA,
            detector_name=self.name,
        )

        if not resp.success:
            return CheckResultV2(
                name=self.name, category=self.category, score=0, weight=self.weight,
                status="error", cost_tokens=resp.usage.total_tokens if resp.usage else 0,
                details=f"请求失败: {resp.error}",
            )

        issues = []
        score = 0

        try:
            data = json.loads(resp.content or "")
            has_name = "name" in data and isinstance(data["name"], str)
            has_age = "age" in data and isinstance(data["age"], int)
            has_city = "city" in data and isinstance(data["city"], str)

            if has_name and has_age and has_city:
                score = 100
            else:
                score = 40
                missing = []
                if not has_name: missing.append("name")
                if not has_age: missing.append("age")
                if not has_city: missing.append("city")
                issues.append(Issue(
                    level=IssueLevel.MAJOR,
                    message=f"缺少必需字段或类型错误: {missing}",
                    detector_name=self.name,
                ))
        except (json.JSONDecodeError, TypeError):
            score = 10
            issues.append(Issue(
                level=IssueLevel.CRITICAL,
                message=f"响应不是有效 JSON: {(resp.content or '')[:100]}",
                detector_name=self.name,
            ))

        return CheckResultV2(
            name=self.name, category=self.category, score=score, weight=self.weight,
            cost_tokens=resp.usage.total_tokens if resp.usage else 0,
            details=f"content={resp.content[:100] if resp.content else 'None'}",
            issues=issues,
        )
