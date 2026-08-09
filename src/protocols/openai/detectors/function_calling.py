"""function_calling - 函数调用能力检测（能力）"""

import json
from src.core.detector_base import ActiveDetector
from src.core.models import CheckResultV2, Issue, IssueLevel
from ..config import WEIGHTS, CATEGORIES


WEATHER_TOOL = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get the current weather in a given location",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "City name"},
            },
            "required": ["location"],
        },
    },
}


class FunctionCallingDetector(ActiveDetector):
    """函数调用检测：验证模型能正确发起 tool_call"""

    name = "function_calling"
    category = CATEGORIES["function_calling"]
    weight = WEIGHTS["function_calling"]
    modes = ["standard", "full"]
    timeout = 30

    def run(self, client) -> CheckResultV2:
        resp = client.chat(
            messages=[{"role": "user", "content": "What's the weather in Tokyo?"}],
            max_tokens=100,
            tools=[WEATHER_TOOL],
            detector_name=self.name,
        )

        if not resp.success:
            return CheckResultV2(
                name=self.name, category=self.category, score=0, weight=self.weight,
                status="error", cost_tokens=resp.usage.total_tokens if resp.usage else 0,
                details=f"请求失败: {resp.error}",
            )

        raw = resp.raw_response or {}
        choice = raw.get("choices", [{}])[0]
        msg = choice.get("message", {})
        tool_calls = msg.get("tool_calls", [])

        issues = []
        score = 0

        if tool_calls:
            # 检查 tool_call 结构
            tc = tool_calls[0]
            fn = tc.get("function", {})

            has_id = bool(tc.get("id"))
            has_name = bool(fn.get("name"))
            has_args = bool(fn.get("arguments"))

            if has_id and has_name and has_args:
                score = 90
                # 检查是否调用了正确的函数
                if fn.get("name") == "get_weather":
                    score = 95
                    # 检查参数
                    try:
                        args = json.loads(fn.get("arguments", "{}"))
                        if "location" in args:
                            score = 100
                    except (json.JSONDecodeError, TypeError):
                        issues.append(Issue(
                            level=IssueLevel.MINOR,
                            message="tool_call arguments 不是有效 JSON",
                            detector_name=self.name,
                        ))
                else:
                    issues.append(Issue(
                        level=IssueLevel.MINOR,
                        message=f"调用了错误函数: {fn.get('name')}",
                        detector_name=self.name,
                    ))
            else:
                score = 50
                if not has_id:
                    issues.append(Issue(level=IssueLevel.MAJOR, message="tool_call 缺少 id", detector_name=self.name))
                if not has_name:
                    issues.append(Issue(level=IssueLevel.MAJOR, message="tool_call 缺少 function.name", detector_name=self.name))
                if not has_args:
                    issues.append(Issue(level=IssueLevel.MAJOR, message="tool_call 缺少 function.arguments", detector_name=self.name))
        else:
            # 没有发起 tool_call
            content = (msg.get("content") or "").lower()
            if "weather" in content or "tokyo" in content:
                score = 30
                issues.append(Issue(level=IssueLevel.MAJOR, message="模型直接回答而非发起 tool_call", detector_name=self.name))
            else:
                score = 10
                issues.append(Issue(level=IssueLevel.CRITICAL, message="模型未发起 function call 也未回答", detector_name=self.name))

        return CheckResultV2(
            name=self.name, category=self.category, score=score, weight=self.weight,
            cost_tokens=resp.usage.total_tokens if resp.usage else 0,
            details=f"tool_calls={len(tool_calls)}, content={msg.get('content', '')[:50]}",
            issues=issues,
        )
