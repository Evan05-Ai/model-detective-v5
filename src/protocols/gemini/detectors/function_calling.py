"""function_calling - 函数调用检测（能力）"""

from src.core.detector_base import ActiveDetector
from src.core.models import CheckResultV2, Issue, IssueLevel
from ..config import WEIGHTS, CATEGORIES


WEATHER_TOOL = [{
    "function_declarations": [{
        "name": "get_weather",
        "description": "Get the current weather in a given location",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "City name"},
            },
            "required": ["location"],
        },
    }],
}]


class FunctionCallingDetector(ActiveDetector):
    """函数调用检测：验证 Gemini function calling 结构"""

    name = "function_calling"
    category = CATEGORIES["function_calling"]
    weight = WEIGHTS["function_calling"]
    modes = ["standard", "full"]
    timeout = 30

    def run(self, client) -> CheckResultV2:
        resp = client.generate(
            contents=[{"parts": [{"text": "What's the weather in Tokyo?"}]}],
            max_tokens=100,
            tools=WEATHER_TOOL,
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

        candidates = raw.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])

            # 查找 functionCall
            func_call = None
            for part in parts:
                if "functionCall" in part:
                    func_call = part["functionCall"]
                    break

            if func_call:
                has_name = func_call.get("name") == "get_weather"
                args = func_call.get("args", {})

                if has_name and "location" in args:
                    score = 100
                elif has_name:
                    score = 80
                    issues.append(Issue(
                        level=IssueLevel.MINOR,
                        message="functionCall 缺少 location 参数",
                        detector_name=self.name,
                    ))
                else:
                    score = 50
                    issues.append(Issue(
                        level=IssueLevel.MAJOR,
                        message=f"调用了错误函数: {func_call.get('name')}",
                        detector_name=self.name,
                    ))
            else:
                # 没有发起 functionCall
                text_parts = [p.get("text", "") for p in parts if "text" in p]
                text = " ".join(text_parts).lower()
                if "weather" in text or "tokyo" in text:
                    score = 30
                    issues.append(Issue(
                        level=IssueLevel.MAJOR,
                        message="模型直接回答而非发起 functionCall",
                        detector_name=self.name,
                    ))
                else:
                    score = 10
                    issues.append(Issue(
                        level=IssueLevel.CRITICAL,
                        message="模型未发起 functionCall 也未回答",
                        detector_name=self.name,
                    ))
        else:
            score = 10
            issues.append(Issue(
                level=IssueLevel.CRITICAL,
                message="响应缺少 candidates",
                detector_name=self.name,
            ))

        return CheckResultV2(
            name=self.name, category=self.category, score=score, weight=self.weight,
            cost_tokens=resp.usage.total_tokens if resp.usage else 0,
            details=f"func_call={'found' if func_call else 'missing'}",
            issues=issues,
        )
