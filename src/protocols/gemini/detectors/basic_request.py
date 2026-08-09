"""basic_request - 基础请求检测（真伪，v2.6 同步版）

v2.6 变更：
  - 使用公共的 model_name_utils 进行模型名规范化
  - 增加置信度系统
"""

import re
from src.core.detector_base import ActiveDetector
from src.core.models import CheckResultV2, Issue, IssueLevel
from src.utils.model_name_utils import normalize_model_name, strip_relay_prefix
from ..config import WEIGHTS, CATEGORIES

# v2.6: 保留本地函数以保持向后兼容
_strip_relay_prefix = strip_relay_prefix
_normalize_model = normalize_model_name


class BasicRequestDetector(ActiveDetector):
    """基础请求检测：发送最小请求验证 Gemini 模型可响应"""

    name = "basic_request"
    category = CATEGORIES["basic_request"]
    weight = WEIGHTS["basic_request"]
    modes = ["quick", "standard", "full"]
    timeout = 15

    def run(self, client) -> CheckResultV2:
        resp = client.generate(
            contents=[{"parts": [{"text": "Say hello in one word."}]}],
            max_tokens=10,
            detector_name=self.name,
        )

        if not resp.success:
            return CheckResultV2(
                name=self.name, category=self.category, score=0, weight=self.weight,
                status="error", cost_tokens=resp.usage.total_tokens if resp.usage else 0,
                confidence=0.0,
                confidence_reason="基础请求检测失败",
                details=f"请求失败: {resp.error}",
                issues=[Issue(level=IssueLevel.CRITICAL, message=f"基础请求失败: {resp.error}", detector_name=self.name)],
            )

        content = resp.content or ""
        model_field = resp.model or ""
        issues = []
        score = 50

        if not content.strip():
            score = 20
            issues.append(Issue(level=IssueLevel.MAJOR, message="响应内容为空", detector_name=self.name))
        else:
            score = 70

        # 检查 model 字段
        claimed = client.model.lower()
        actual = model_field.lower()
        claimed_norm = _normalize_model(claimed)
        actual_norm = _normalize_model(actual)

        if actual == claimed:
            score = 95
        elif claimed in actual or actual in claimed:
            score = 80
        elif claimed_norm == actual_norm and claimed_norm:
            score = 75
            issues.append(Issue(
                level=IssueLevel.MINOR,
                message=f"模型名格式略有差异（声称 {client.model}，实际 {model_field}），但规范化后匹配，可能是中转站自定义命名",
                detector_name=self.name,
            ))
        elif actual_norm and claimed_norm and (claimed_norm in actual_norm or actual_norm in claimed_norm):
            score = 70
            issues.append(Issue(
                level=IssueLevel.MINOR,
                message=f"模型名部分匹配（声称 {client.model}，实际 {model_field}），可能是中转站自定义命名或别名",
                detector_name=self.name,
            ))
        elif actual and actual != claimed:
            score = 40
            issues.append(Issue(
                level=IssueLevel.MAJOR,
                message=f"model 字段不匹配：声称 {client.model}，实际返回 {model_field}。这可能意味着中转站使用了不同的模型来响应请求",
                detector_name=self.name,
            ))

        # v2.6: 根据匹配程度确定置信度
        if score >= 90:
            confidence = 0.95
            confidence_reason = "模型名称完全匹配，响应结构完整"
        elif score >= 75:
            confidence = 0.85
            confidence_reason = "模型名称基本匹配，可能存在格式差异"
        elif score >= 50:
            confidence = 0.7
            confidence_reason = "模型名称部分匹配或存在轻微异常"
        else:
            confidence = 0.8
            confidence_reason = "模型名称明显不匹配或响应结构异常"

        return CheckResultV2(
            name=self.name, category=self.category, score=score, weight=self.weight,
            cost_tokens=resp.usage.total_tokens if resp.usage else 0,
            confidence=confidence,
            confidence_reason=confidence_reason,
            details=f"model={model_field}, content={content[:50]}",
            issues=issues,
        )
