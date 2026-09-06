"""message_id - 消息 ID 前缀校验（合规，v3.0.2 转为被动检测器）

v3.0.2 变更：
  - ActiveDetector → PassiveDetector：不再自发请求（省 1 请求/模型），
    改为观察其他检测器响应中的 message id。standard 模式下可观察到
    ~10 个 id，样本量反而比原先自发的 1 次请求更多。
  - 评分语义与旧版一致：缺少 id → 30；前缀非 msg_ → 20 (CRITICAL)；
    id 主体过短 → 60 (MINOR)；tool_use 前缀非 toolu_ → -20 (MAJOR)。
  - 新增：多个请求返回相同 message id（重放/网关缓存特征）→ MINOR -10。
"""

from src.core.detector_base import PassiveDetector
from src.core.models import CheckResultV2, Issue, IssueLevel
from ..config import WEIGHTS, CATEGORIES


class MessageIdDetector(PassiveDetector):
    """消息 ID 检测：验证响应 ID 符合 Claude 前缀规范（msg_/toolu_/srvtoolu_）"""

    name = "message_id"
    category = CATEGORIES["message_id"]
    weight = WEIGHTS["message_id"]
    modes = ["standard", "full"]

    def finalize(self) -> CheckResultV2:
        issues = []
        score = 100
        seen_ids = []
        observed_responses = 0
        worst_details_id = ""

        for _req, resp, _det_name in self._observations:
            if not resp.get("success"):
                continue
            raw = resp.get("raw") or {}
            msg_id = raw.get("id") or ""
            if not msg_id:
                continue
            observed_responses += 1
            seen_ids.append(msg_id)

            # 检查消息 ID 前缀（取最差结果）
            if not msg_id.startswith("msg_"):
                score = min(score, 20)
                issues.append(Issue(
                    level=IssueLevel.CRITICAL,
                    message=f"消息 ID 前缀不是 'msg_': {msg_id[:20]}",
                    detector_name=self.name,
                ))
            else:
                id_body = msg_id[4:]
                if len(id_body) < 10:
                    score = min(score, 60)
                    issues.append(Issue(
                        level=IssueLevel.MINOR,
                        message=f"消息 ID 过短: {msg_id}",
                        detector_name=self.name,
                    ))
                elif score == 100:
                    worst_details_id = worst_details_id or msg_id

            # 检查 tool_use ID 前缀（如果有）
            for block in raw.get("content", []) or []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    tool_id = block.get("id", "")
                    if tool_id and not tool_id.startswith("toolu_"):
                        score -= 20
                        issues.append(Issue(
                            level=IssueLevel.MAJOR,
                            message=f"tool_use ID 前缀不是 'toolu_': {tool_id[:20]}",
                            detector_name=self.name,
                        ))

        if observed_responses == 0:
            return CheckResultV2(
                name=self.name, category=self.category,
                score=20, weight=self.weight,
                confidence=0.0,
                confidence_reason="未观察到任何携带 message id 的成功响应",
                details="未观察到任何请求响应，无法进行消息 ID 校验",
                issues=[Issue(
                    level=IssueLevel.MAJOR,
                    message="未观察到任何检测器响应，无法校验消息 ID 规范",
                    detector_name=self.name,
                )],
            )

        # 重放特征：不同请求返回相同 message id
        unique_ids = set(seen_ids)
        if len(unique_ids) < len(seen_ids):
            score = max(0, score - 10)
            issues.append(Issue(
                level=IssueLevel.MINOR,
                message=f"{len(seen_ids)} 次请求中出现重复 message id（可能是网关缓存或重放）",
                detector_name=self.name,
            ))

        score = max(0, score)

        # 置信度随样本量提升
        if observed_responses >= 5:
            confidence, conf_reason = 0.95, f"{observed_responses} 个响应的 message id 均已校验"
        elif observed_responses >= 2:
            confidence, conf_reason = 0.85, f"{observed_responses} 个响应的 message id 已校验"
        else:
            confidence, conf_reason = 0.6, "仅观察到 1 个 message id"

        if score == 100:
            issues.append(Issue(
                level=IssueLevel.OK,
                message=f"{observed_responses} 个响应的 message id 均符合 msg_ 前缀规范，原生 Anthropic 链路特征",
                detector_name=self.name,
            ))

        return CheckResultV2(
            name=self.name, category=self.category,
            score=score, weight=self.weight,
            confidence=confidence,
            confidence_reason=conf_reason,
            details=f"观察到 {observed_responses} 个 message id（如 {worst_details_id[:30] or 'N/A'}），"
                    f"唯一 id {len(unique_ids)} 个",
            issues=issues,
        )
