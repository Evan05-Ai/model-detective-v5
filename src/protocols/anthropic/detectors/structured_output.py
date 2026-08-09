"""structured_output - 结构化输出检测（能力）"""

import json
from src.core.detector_base import ActiveDetector
from src.core.models import CheckResultV2, Issue, IssueLevel
from ..config import WEIGHTS, CATEGORIES


class StructuredOutputDetector(ActiveDetector):
    """结构化输出检测：验证 Claude tool_use 强制结构化输出"""

    name = "structured_output"
    category = CATEGORIES["structured_output"]
    weight = WEIGHTS["structured_output"]
    modes = ["full"]
    timeout = 30

    EXTRACT_TOOL = {
        "name": "extract_person",
        "description": "Extract person information from text",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Person's name"},
                "age": {"type": "integer", "description": "Person's age"},
                "city": {"type": "string", "description": "Person's city"},
            },
            "required": ["name", "age", "city"],
        },
    }

    def run(self, client) -> CheckResultV2:
        resp = client.messages(
            messages=[{
                "role": "user",
                "content": "John is 30 years old and lives in New York. Extract his information using the tool.",
            }],
            max_tokens=200,
            tools=[self.EXTRACT_TOOL],
            tool_choice={"type": "tool", "name": "extract_person"},
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
        score = 0

        # 查找 tool_use content block
        tool_use_block = None
        for block in raw.get("content", []):
            if block.get("type") == "tool_use":
                tool_use_block = block
                break

        if tool_use_block:
            has_id = bool(tool_use_block.get("id"))
            has_name = tool_use_block.get("name") == "extract_person"
            input_data = tool_use_block.get("input", {})

            if has_id and has_name:
                score = 80
                # 验证提取的数据
                if input_data.get("name") == "John" and input_data.get("age") == 30 and input_data.get("city") == "New York":
                    score = 100
                elif input_data.get("name") or input_data.get("age") or input_data.get("city"):
                    score = 70
                    issues.append(Issue(
                        level=IssueLevel.MINOR,
                        message=f"部分提取正确: {input_data}",
                        detector_name=self.name,
                    ))
                else:
                    score = 40
                    issues.append(Issue(
                        level=IssueLevel.MAJOR,
                        message=f"tool_use input 为空或错误: {input_data}",
                        detector_name=self.name,
                    ))
            else:
                score = 50
                if not has_id:
                    issues.append(Issue(level=IssueLevel.MAJOR, message="tool_use 缺少 id", detector_name=self.name))
                if not has_name:
                    issues.append(Issue(level=IssueLevel.MAJOR, message="tool_use name 不正确", detector_name=self.name))
        else:
            score = 10
            issues.append(Issue(
                level=IssueLevel.CRITICAL,
                message="未返回 tool_use content block",
                detector_name=self.name,
            ))

        return CheckResultV2(
            name=self.name, category=self.category, score=score, weight=self.weight,
            cost_tokens=resp.usage.total_tokens if resp.usage else 0,
            details=f"tool_use={'found' if tool_use_block else 'missing'}",
            issues=issues,
        )
