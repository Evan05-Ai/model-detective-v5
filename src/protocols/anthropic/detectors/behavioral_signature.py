"""behavioral_signature - 行为指纹检测（真伪，v2.6 重构版）

v2.6 重大变更：
  - 降低权重至 0.04（原 0.08），减少过拟合影响
  - 移除主观短语检测（"here are", "certainly" 等）
  - 移除非 Claude 特征判定（"sure thing" 等）
  - 仅保留客观的结构化输出检测
  - 评分更加保守，避免误判真实模型

设计理念：
  - 行为指纹只能作为辅助参考，不能作为判定依据
  - Claude 的系统提示差异会导致行为差异，不能因此扣分
  - 只检测"是否具备结构化输出能力"，不检测"是否符合预期风格"
"""

from src.core.detector_base import ActiveDetector
from src.core.models import CheckResultV2, Issue, IssueLevel
from ..config import WEIGHTS, CATEGORIES


class BehavioralSignatureDetector(ActiveDetector):
    """行为指纹检测：客观分析模型的结构化输出能力（v2.6 保守版）"""

    name = "behavioral_signature"
    category = CATEGORIES["behavioral_signature"]
    weight = WEIGHTS["behavioral_signature"]
    modes = ["standard", "full"]
    timeout = 30
    estimated_tokens = 400

    def run(self, client) -> CheckResultV2:
        # 发送能触发格式化响应的请求
        resp = client.messages(
            messages=[{
                "role": "user",
                "content": "List 3 benefits of exercise. Use a numbered list with brief explanations."
            }],
            max_tokens=200,
            detector_name=self.name,
        )

        if not resp.success:
            return CheckResultV2(
                name=self.name, category=self.category, score=0, weight=self.weight,
                status="error", cost_tokens=resp.usage.total_tokens if resp.usage else 0,
                details=f"请求失败: {resp.error}",
            )

        content = resp.content or ""
        issues = []
        
        # v2.6: 保守评分策略 - 只检测结构化能力，不判定风格
        # 基础分 60（及格线），有结构化特征加分，无特征不扣分
        score = 60
        
        # 1. 检测编号列表（客观特征）
        has_numbered_list = bool(
            any(line.strip().startswith(f"{i}.") for i in range(1, 10) for line in content.split("\n"))
        )
        
        # 2. 检测 Markdown 加粗（客观特征）
        has_bold = "**" in content
        
        # 3. 检测列表项（客观特征）
        has_list_items = any(line.strip().startswith(("- ", "* ", "• ")) for line in content.split("\n"))
        
        # 结构化能力评分（仅加分，不扣分）
        structure_score = 0
        if has_numbered_list:
            structure_score += 15
        if has_bold:
            structure_score += 10
        if has_list_items:
            structure_score += 10
            
        score = min(85, 60 + structure_score)  # 最高 85，不给予满分避免过度自信
        
        # 响应长度检查（仅极端情况扣分）
        if len(content) < 30:
            score = max(30, score - 20)
            issues.append(Issue(
                level=IssueLevel.MINOR,
                message="响应过短，可能未完整理解指令",
                detector_name=self.name,
            ))
        elif len(content) > 500:
            # 响应过长，但只是提示，不扣分
            issues.append(Issue(
                level=IssueLevel.MINOR,
                message="响应较长，但结构化输出正常",
                detector_name=self.name,
            ))
        
        # v2.6: 移除主观短语检测和非 Claude 特征判定
        # 原因：系统提示差异会导致行为差异，不能作为真伪判定依据
        
        if score >= 70:
            issues.append(Issue(
                level=IssueLevel.OK,
                message=f"模型具备结构化输出能力（编号列表={has_numbered_list}, 加粗={has_bold}, 列表项={has_list_items}）",
                detector_name=self.name,
            ))
        else:
            issues.append(Issue(
                level=IssueLevel.MINOR,
                message="模型结构化输出能力一般，但这不表示模型非真实",
                detector_name=self.name,
            ))

        return CheckResultV2(
            name=self.name, category=self.category, score=score, weight=self.weight,
            cost_tokens=resp.usage.total_tokens if resp.usage else 0,
            details=f"numbered_list={has_numbered_list}, bold={has_bold}, list_items={has_list_items}, len={len(content)}",
            issues=issues,
        )
