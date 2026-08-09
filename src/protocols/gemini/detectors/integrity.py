"""integrity - 一致性检测（合规，PassiveDetector）

v2.4 修复：模型名规范化比较 + 根据成功率动态评分
"""

import re
from src.core.detector_base import PassiveDetector
from src.core.models import CheckResultV2, Issue, IssueLevel
from ..config import WEIGHTS, CATEGORIES


def _normalize_model_name(name: str) -> str:
    """规范化模型名称：移除所有非字母数字字符，统一比较"""
    return re.sub(r'[^a-z0-9]', '', name.lower())


class IntegrityDetector(PassiveDetector):
    """一致性检测：观察其他检测器的请求/响应"""

    name = "integrity"
    category = CATEGORIES["integrity"]
    weight = WEIGHTS["integrity"]
    modes = ["standard", "full"]

    def finalize(self) -> CheckResultV2:
        issues = []

        models_raw = set()
        models_normalized = set()
        success_count = 0
        total_obs = len(self._observations)

        for req, resp, det_name in self._observations:
            m = resp.get("model")
            if m:
                models_raw.add(m)
                models_normalized.add(_normalize_model_name(m))
            if resp.get("success"):
                success_count += 1

        if total_obs == 0:
            score = 20
            issues.append(Issue(
                level=IssueLevel.MAJOR,
                message="未观察到任何检测器请求，无法进行一致性评估",
                detector_name=self.name,
            ))
        else:
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
                issues.append(Issue(
                    level=IssueLevel.MINOR,
                    message=f"{total_obs - success_count}/{total_obs} 个检测器请求失败",
                    detector_name=self.name,
                ))
            else:
                score = 70

            if len(models_normalized) > 1:
                score -= 25
                issues.append(Issue(
                    level=IssueLevel.MAJOR,
                    message=f"不同请求返回了不同的模型名称: {models_raw}。"
                            f"这通常意味着中转站后端使用了多个不同的模型来响应请求，"
                            f"可能是负载均衡切换或模型替换。",
                    detector_name=self.name,
                ))
            elif len(models_normalized) == 1 and len(models_raw) > 1:
                score -= 5
                issues.append(Issue(
                    level=IssueLevel.MINOR,
                    message=f"模型名称格式不一致: {models_raw}。"
                            f"实际是同一模型，仅命名格式不同，影响较小。",
                    detector_name=self.name,
                ))
            elif len(models_normalized) == 1:
                score = min(100, score + 10)

        score = max(0, score)

        return CheckResultV2(
            name=self.name, category=self.category, score=score, weight=self.weight,
            details=f"共观察 {total_obs} 次请求（{success_count} 次成功），"
                    f"模型名称: {models_raw}",
            issues=issues,
        )
