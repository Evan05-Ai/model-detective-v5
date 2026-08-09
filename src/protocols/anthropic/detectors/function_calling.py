"""function_calling - 函数调用检测（能力）"""

from src.core.detector_base import ActiveDetector
from src.core.models import CheckResultV2, Issue, IssueLevel
from ..config import WEIGHTS, CATEGORIES


WEATHER_TOOL = {
    "name": "get_weather",
    "description": "Get the current weather in a given location",
    "input_schema": {
        "type": "object",
        "properties": {
            "location": {"type": "string", "description": "City name"},
        },
        "required": ["location"],
    },
}


class FunctionCallingDetector(ActiveDetector):
    """函数调用检测：验证 Claude tool_use 结构"""

    name = "function_calling"
    category = CATEGORIES["function_calling"]
    weight = WEIGHTS["function_calling"]
    modes = ["standard", "full"]
    timeout = 30
    estimated_tokens = 500  # v2.5: prompt + tools schema ~300 tokens + output ~200 tokens

    def run(self, client) -> CheckResultV2:
        resp = client.messages(
            messages=[{"role": "user", "content": "What's the weather in Paris?"}],
            max_tokens=200,
            tools=[WEATHER_TOOL],
            detector_name=self.name,
        )

        if not resp.success:
            return CheckResultV2(
                name=self.name, category=self.category, score=0, weight=self.weight,
                status="error", cost_tokens=resp.usage.total_tokens if resp.usage else 0,
                confidence=0.0,
                confidence_reason="函数调用检测请求失败",
                details=f"请求失败: {resp.error}",
                issues=[Issue(
                    level=IssueLevel.MAJOR,
                    message=f"函数调用检测请求失败: {resp.error}",
                    detector_name=self.name,
                )],
            )

        raw = resp.raw_response or {}
        issues = []
        score = 0

        tool_use_block = None
        for block in raw.get("content", []):
            if block.get("type") == "tool_use":
                tool_use_block = block
                break

        if tool_use_block:
            has_id = bool(tool_use_block.get("id"))
            has_name = tool_use_block.get("name") == "get_weather"
            input_data = tool_use_block.get("input", {})

            # 检查 id 前缀（Claude 使用 toolu_ 前缀）
            tool_id = tool_use_block.get("id", "")
            has_correct_prefix = tool_id.startswith("toolu_")

            if has_id and has_name and has_correct_prefix:
                score = 95
                confidence = 0.95
                confidence_reason = "tool_use 结构完整，ID 前缀正确"
                if "location" in input_data:
                    score = 100
                    confidence = 0.98
                    confidence_reason = "tool_use 结构完整，参数提取正确"
            elif has_id and has_name:
                score = 70
                confidence = 0.8
                confidence_reason = "tool_use 结构基本完整，但 ID 前缀非标准格式"
                issues.append(Issue(
                    level=IssueLevel.MINOR,
                    message=f"tool_use id 前缀不是 'toolu_': {tool_id}",
                    detector_name=self.name,
                ))
            else:
                score = 40
                confidence = 0.75
                confidence_reason = "tool_use 结构不完整"
                issues.append(Issue(
                    level=IssueLevel.MAJOR,
                    message=f"tool_use 结构不完整: id={has_id}, name={has_name}",
                    detector_name=self.name,
                ))
        else:
            score = 15
            confidence = 0.7
            confidence_reason = "模型未发起 tool_use，可能不支持函数调用"
            issues.append(Issue(
                level=IssueLevel.CRITICAL,
                message="模型未发起 tool_use",
                detector_name=self.name,
            ))

        return CheckResultV2(
            name=self.name, category=self.category, score=score, weight=self.weight,
            cost_tokens=resp.usage.total_tokens if resp.usage else 0,
            confidence=confidence,
            confidence_reason=confidence_reason,
            details=f"tool_use={'found' if tool_use_block else 'missing'}, id_prefix={tool_use_block.get('id', '')[:6] if tool_use_block else 'N/A'}",
            issues=issues,
        )
