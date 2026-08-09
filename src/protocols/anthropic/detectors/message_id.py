"""message_id - 消息 ID 前缀校验（合规）"""

from src.core.detector_base import ActiveDetector
from src.core.models import CheckResultV2, Issue, IssueLevel
from ..config import WEIGHTS, CATEGORIES


# Claude 消息 ID 前缀规范
VALID_ID_PREFIXES = ["msg_"]
VALID_TOOL_USE_PREFIXES = ["toolu_"]
VALID_SERVER_TOOL_USE_PREFIXES = ["srvtoolu_"]


class MessageIdDetector(ActiveDetector):
    """消息 ID 检测：验证响应 ID 符合 Claude 前缀规范（msg_/toolu_/srvtoolu_）"""

    name = "message_id"
    category = CATEGORIES["message_id"]
    weight = WEIGHTS["message_id"]
    modes = ["standard", "full"]
    timeout = 15
    estimated_tokens = 100  # v2.5: minimal request, ~100 tokens

    def run(self, client) -> CheckResultV2:
        resp = client.messages(
            messages=[{"role": "user", "content": "Say hello."}],
            max_tokens=10,
            detector_name=self.name,
        )

        if not resp.success:
            return CheckResultV2(
                name=self.name, category=self.category, score=0, weight=self.weight,
                status="error", cost_tokens=resp.usage.total_tokens if resp.usage else 0,
                details=f"请求失败: {resp.error}",
            )

        issues = []
        score = 100
        msg_id = resp.message_id or ""

        # 检查消息 ID 前缀
        if not msg_id:
            score = 30
            issues.append(Issue(
                level=IssueLevel.MAJOR,
                message="响应缺少 id 字段",
                detector_name=self.name,
            ))
        elif not msg_id.startswith("msg_"):
            score = 20
            issues.append(Issue(
                level=IssueLevel.CRITICAL,
                message=f"消息 ID 前缀不是 'msg_': {msg_id[:20]}",
                detector_name=self.name,
            ))
        else:
            # 检查 ID 格式合理性（msg_ 后应有足够长度的随机字符）
            id_body = msg_id[4:]
            if len(id_body) < 10:
                score = 60
                issues.append(Issue(
                    level=IssueLevel.MINOR,
                    message=f"消息 ID 过短: {msg_id}",
                    detector_name=self.name,
                ))

        # 检查 tool_use ID 前缀（如果有）
        raw = resp.raw_response or {}
        for block in raw.get("content", []):
            if block.get("type") == "tool_use":
                tool_id = block.get("id", "")
                if tool_id and not tool_id.startswith("toolu_"):
                    score -= 20
                    issues.append(Issue(
                        level=IssueLevel.MAJOR,
                        message=f"tool_use ID 前缀不是 'toolu_': {tool_id[:20]}",
                        detector_name=self.name,
                    ))

        score = max(0, score)

        return CheckResultV2(
            name=self.name, category=self.category, score=score, weight=self.weight,
            cost_tokens=resp.usage.total_tokens if resp.usage else 0,
            details=f"msg_id={msg_id[:30]}",
            issues=issues,
        )
