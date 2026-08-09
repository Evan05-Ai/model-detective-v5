"""integrity - 一致性检测（合规，PassiveDetector，v2.6 重构版）

v2.4 修复：
  1. 当大多数检测器请求失败时，integrity 不能给默认 80 分
  2. 模型名规范化比较：claude-opus-4-8 和 claude-opus-4.8 视为同一模型
     （仅连字符/点号格式差异，不是不同模型）

v2.6 变更：
  - 使用公共的 model_name_utils 进行模型名规范化
  - 增加置信度系统
  - 权重提升至 0.08（原 0.06）
"""

from src.core.detector_base import PassiveDetector
from src.core.models import CheckResultV2, Issue, IssueLevel
from src.utils.model_name_utils import normalize_model_name
from ..config import WEIGHTS, CATEGORIES


class IntegrityDetector(PassiveDetector):
    """一致性检测：观察其他检测器的请求/响应，检查一致性"""

    name = "integrity"
    category = CATEGORIES["integrity"]
    weight = WEIGHTS["integrity"]
    modes = ["standard", "full"]

    def finalize(self) -> CheckResultV2:
        issues = []

        # 收集所有观察到的数据
        models_raw = set()        # 原始模型名
        models_normalized = set()  # 规范化后的模型名
        contents = []
        success_count = 0
        total_obs = len(self._observations)

        for req, resp, det_name in self._observations:
            m = resp.get("model")
            if m:
                models_raw.add(m)
                models_normalized.add(normalize_model_name(m))
            c = resp.get("content", "")
            if c:
                contents.append(c.strip().lower())
            if resp.get("success"):
                success_count += 1

        # 根据观察数据的质量和数量动态评分
        confidence = 0.5  # 基础置信度
        confidence_reason = ""
        
        if total_obs == 0:
            score = 20
            confidence = 0.0
            confidence_reason = "未观察到任何检测器请求"
            issues.append(Issue(
                level=IssueLevel.MAJOR,
                message="未观察到任何检测器请求，无法进行一致性评估",
                detector_name=self.name,
            ))
        else:
            # 根据成功率动态调整基础分
            success_ratio = success_count / total_obs
            if success_ratio < 0.3:
                score = 30
                issues.append(Issue(
                    level=IssueLevel.MAJOR,
                    message=f"{total_obs - success_count}/{total_obs} 个检测器请求失败，"
                            f"观察数据不完整，一致性评估结果仅供参考",
                    detector_name=self.name,
                ))
            elif success_ratio < 0.6:
                score = 50
                confidence = 0.6
                issues.append(Issue(
                    level=IssueLevel.MINOR,
                    message=f"{total_obs - success_count}/{total_obs} 个检测器请求失败",
                    detector_name=self.name,
                ))
            else:
                score = 70
                confidence = 0.8

            # model 字段一致性检查（使用规范化名称比较）
            # v2.6: 优化评分逻辑，充分考虑观察次数和一致性程度
            if len(models_normalized) > 1:
                # 多个不同模型 - 根据不一致的比例扣分
                inconsistency_ratio = len(models_normalized) / max(len(models_raw), 1)
                if inconsistency_ratio > 0.5:
                    score -= 30
                    confidence = 0.9  # 高置信度：明确检测到不一致
                    confidence_reason = f"明确检测到 {len(models_normalized)} 种不同模型名称"
                    issues.append(Issue(
                        level=IssueLevel.MAJOR,
                        message=f"严重不一致：检测到 {len(models_normalized)} 种不同的模型名称: {models_raw}。"
                                f"这强烈暗示中转站使用了多个不同的后端模型，可能存在模型替换或负载均衡问题。",
                        detector_name=self.name,
                    ))
                else:
                    score -= 15
                    confidence = 0.75
                    confidence_reason = f"检测到 {len(models_normalized)} 种模型名称变体"
                    issues.append(Issue(
                        level=IssueLevel.MINOR,
                        message=f"轻微不一致：检测到 {len(models_normalized)} 种模型名称变体: {models_raw}。"
                                f"可能是同一模型的不同命名格式。",
                        detector_name=self.name,
                    ))
            elif len(models_normalized) == 1 and len(models_raw) > 1:
                # 规范化后相同但原始格式不同（如 claude-opus-4-8 vs claude-opus-4.8）
                score -= 3  # v2.6: 轻微扣分，因为只是格式问题
                confidence = 0.85
                confidence_reason = "模型名称规范化后一致，仅格式差异"
                issues.append(Issue(
                    level=IssueLevel.MINOR,
                    message=f"模型名称格式不一致: {models_raw}。"
                            f"实际是同一模型，仅命名格式不同，影响很小。",
                    detector_name=self.name,
                ))
            elif len(models_normalized) == 1:
                # 完全一致的模型名称 - 根据观察次数给予奖励
                # v2.6: 观察次数越多、一致性越好，得分越高，置信度也越高
                consistency_bonus = min(15, total_obs * 2)  # 每次观察+2分，最多+15
                score = min(100, score + 10 + consistency_bonus)
                
                # 根据观察次数调整置信度
                if total_obs >= 10:
                    confidence = 0.95
                    confidence_reason = f"优秀的一致性：{total_obs} 次请求全部返回相同模型名称"
                    issues.append(Issue(
                        level=IssueLevel.OK,
                        message=f"优秀的一致性：{total_obs} 次请求全部返回相同的模型名称 '{list(models_raw)[0]}'，"
                                f"说明后端模型非常稳定，没有负载均衡切换或模型替换。",
                        detector_name=self.name,
                    ))
                elif total_obs >= 5:
                    confidence = 0.9
                    confidence_reason = f"良好的一致性：{total_obs} 次请求返回相同模型名称"
                    issues.append(Issue(
                        level=IssueLevel.OK,
                        message=f"良好的一致性：{total_obs} 次请求返回相同的模型名称，后端稳定。",
                        detector_name=self.name,
                    ))
                else:
                    confidence = 0.8
                    confidence_reason = f"模型名称一致：{total_obs} 次请求"
                    issues.append(Issue(
                        level=IssueLevel.OK,
                        message=f"模型名称一致：{total_obs} 次请求返回 '{list(models_raw)[0]}'。",
                        detector_name=self.name,
                    ))

            # 检查是否有异常的空响应
            empty_count = sum(1 for c in contents if not c)
            if empty_count > 0 and len(contents) > 2:
                score -= 15
                issues.append(Issue(
                    level=IssueLevel.MINOR,
                    message=f"{empty_count}/{len(contents)} 个响应内容为空",
                    detector_name=self.name,
                ))

        score = max(0, score)
        confidence = max(0.0, min(1.0, confidence))
        
        if not confidence_reason:
            confidence_reason = f"基于 {total_obs} 次观察的综合评估"

        return CheckResultV2(
            name=self.name, category=self.category, score=score, weight=self.weight,
            confidence=round(confidence, 2),
            confidence_reason=confidence_reason,
            details=f"共观察 {total_obs} 次请求（{success_count} 次成功），"
                    f"模型名称: {models_raw}",
            issues=issues,
        )
