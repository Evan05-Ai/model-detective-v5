"""protocol - 协议合规检测（合规）"""

from src.core.detector_base import ActiveDetector
from src.core.models import CheckResultV2, Issue, IssueLevel
from ..config import WEIGHTS, CATEGORIES


class ProtocolDetector(ActiveDetector):
    """协议合规检测：验证响应结构符合 Anthropic Messages API 规范"""

    name = "protocol"
    category = CATEGORIES["protocol"]
    weight = WEIGHTS["protocol"]
    modes = ["quick", "standard", "full"]
    timeout = 20
    estimated_tokens = 100  # v2.5: minimal request, ~100 tokens

    def run(self, client) -> CheckResultV2:
        resp = client.messages(
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=10,
            detector_name=self.name,
        )

        if not resp.success:
            return CheckResultV2(
                name=self.name, category=self.category, score=0, weight=self.weight,
                status="error", cost_tokens=resp.usage.total_tokens if resp.usage else 0,
                confidence=0.0,
                confidence_reason="协议合规检测请求失败",
                details=f"请求失败: {resp.error}",
                issues=[Issue(
                    level=IssueLevel.MAJOR,
                    message=f"协议合规检测请求失败: {resp.error}",
                    detector_name=self.name,
                )],
            )

        raw = resp.raw_response or {}
        issues = []
        score = 100

        # 检查必需字段
        required_fields = ["id", "type", "role", "content", "model", "stop_reason", "usage"]
        for field in required_fields:
            if field not in raw:
                score -= 15
                issues.append(Issue(
                    level=IssueLevel.MAJOR,
                    message=f"响应缺少必需字段: {field}",
                    detector_name=self.name,
                ))

        # 检查 type 字段
        if raw.get("type") != "message":
            score -= 15
            issues.append(Issue(
                level=IssueLevel.MAJOR,
                message=f"type 字段不是 'message': {raw.get('type')}",
                detector_name=self.name,
            ))

        # 检查 role 字段
        if raw.get("role") != "assistant":
            score -= 10
            issues.append(Issue(
                level=IssueLevel.MINOR,
                message=f"role 字段不是 'assistant': {raw.get('role')}",
                detector_name=self.name,
            ))

        # 检查 content blocks 结构
        content = raw.get("content", [])
        if content:
            for block in content:
                if "type" not in block:
                    score -= 10
                    issues.append(Issue(level=IssueLevel.MINOR, message="content block 缺少 type", detector_name=self.name))
                if block.get("type") == "text" and "text" not in block:
                    score -= 10
                    issues.append(Issue(level=IssueLevel.MINOR, message="text block 缺少 text 字段", detector_name=self.name))

        # 检查 usage 结构
        usage = raw.get("usage", {})
        if usage:
            for uf in ["input_tokens", "output_tokens"]:
                if uf not in usage:
                    score -= 5
                    issues.append(Issue(level=IssueLevel.MINOR, message=f"usage 缺少 {uf}", detector_name=self.name))

        # 检查 stop_reason
        if raw.get("stop_reason") not in ["end_turn", "max_tokens", "stop_sequence", "tool_use"]:
            score -= 10
            issues.append(Issue(
                level=IssueLevel.MINOR,
                message=f"stop_reason 异常: {raw.get('stop_reason')}",
                detector_name=self.name,
            ))

        score = max(0, score)
        
        # v2.6: 根据得分确定置信度
        if score >= 90:
            confidence = 0.95
            confidence_reason = "协议响应结构完整，符合 Anthropic Messages API 规范"
        elif score >= 70:
            confidence = 0.8
            confidence_reason = "协议响应基本合规，存在轻微字段缺失"
        elif score >= 50:
            confidence = 0.7
            confidence_reason = "协议响应部分合规，存在字段缺失"
        else:
            confidence = 0.75  # 低分但高置信度：明确检测到不合规
            confidence_reason = "协议响应明显不合规，结构严重偏离规范"

        return CheckResultV2(
            name=self.name, category=self.category, score=score, weight=self.weight,
            cost_tokens=resp.usage.total_tokens if resp.usage else 0,
            confidence=confidence,
            confidence_reason=confidence_reason,
            details=f"协议合规检查完成, score={score}",
            issues=issues,
        )
