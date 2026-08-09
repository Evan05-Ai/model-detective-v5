"""model_info - 模型信息检测（真伪）"""

from src.core.detector_base import ActiveDetector
from src.core.models import CheckResultV2, Issue, IssueLevel
from ..config import WEIGHTS, CATEGORIES


class ModelInfoDetector(ActiveDetector):
    """模型信息检测：验证 Gemini 模型列表和 modelVersion 字段"""

    name = "model_info"
    category = CATEGORIES["model_info"]
    weight = WEIGHTS["model_info"]
    modes = ["quick", "standard", "full"]
    timeout = 15

    def run(self, client) -> CheckResultV2:
        # 查询模型列表
        success, models, error = client.list_models()
        issues = []
        score = 50

        if not success:
            score = 30
            issues.append(Issue(
                level=IssueLevel.MINOR,
                message=f"无法查询模型列表: {error}",
                detector_name=self.name,
            ))
        else:
            claimed = client.model.lower()
            models_lower = [m.lower() for m in models]

            # 精确匹配
            if claimed in models_lower:
                score = 85
            # 模糊匹配
            elif any(claimed in m or m in claimed for m in models_lower):
                score = 70
            else:
                score = 35
                issues.append(Issue(
                    level=IssueLevel.MAJOR,
                    message=f"声称模型 '{client.model}' 不在模型列表中",
                    detector_name=self.name,
                ))

        # 同时发送请求检查 modelVersion
        resp = client.generate(
            contents=[{"parts": [{"text": "Hi"}]}],
            max_tokens=5,
            detector_name=self.name,
        )

        total_tokens = 0
        if resp.success:
            total_tokens = resp.usage.total_tokens if resp.usage else 0
            model_version = (resp.model or "").lower()
            claimed = client.model.lower()

            if model_version == claimed:
                score = min(100, score + 10)
            elif model_version and claimed not in model_version:
                score = min(score, 40)
                issues.append(Issue(
                    level=IssueLevel.MAJOR,
                    message=f"modelVersion 不匹配: 声称 {client.model}, 实际 {resp.model}",
                    detector_name=self.name,
                ))

        return CheckResultV2(
            name=self.name, category=self.category, score=score, weight=self.weight,
            cost_tokens=total_tokens,
            details=f"models_found={success}, model_version={resp.model if resp.success else 'N/A'}",
            issues=issues,
        )
