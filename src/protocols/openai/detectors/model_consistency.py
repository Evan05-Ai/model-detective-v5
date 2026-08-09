"""model_consistency - 模型一致性检测（真伪，v2.7 重构版）

v2.7 变更（同步 Anthropic consistency v2.7）：
  - 问题改为创意写作（haiku），避免数学问题的确定性陷阱
  - 多维度加权评分：答案一致性40% + 特征稳定性30% + 语义相似度30%
  - 保留 OpenAI 协议特有的模型名一致性检查（作为评分修饰符）
  - 渐进式评分，消除二元化跳跃
  - 评分逻辑共享 src.utils.consistency_scorer

v2.6 变更：
  - 使用公共的 model_name_utils 进行模型名规范化
  - 增加置信度系统
  - 样本量从 2 次增加到 3 次
"""

from src.core.detector_base import ActiveDetector
from src.core.models import CheckResultV2, Issue, IssueLevel
from src.core.error_standards import create_error_result, ErrorScore
from src.utils.model_name_utils import normalize_model_name
from src.utils.consistency_scorer import (
    HAIKU_QUESTION,
    score_responses,
    calc_confidence,
    generate_issues,
)
from ..config import WEIGHTS, CATEGORIES
from src.signatures import (
    REAL_OPENAI_MODELS, FAKE_MODEL_PATTERNS, KNOWN_OPEN_SOURCE_MODELS,
)


class ModelConsistencyDetector(ActiveDetector):
    """模型一致性检测：多次请求验证响应稳定性 + 模型名一致性（v2.7）

    v2.7 评分结构：
    1. 三维度内容评分（40%+30%+30%）通过 consistency_scorer 计算
    2. 模型名一致性作为评分修饰符：
       - 模型名一致且匹配声称 -> 无惩罚
       - 模型名一致但不匹配声称 -> -15
       - 模型名不一致 -> -30
       - 检测到假模型 -> 封顶 15 分
       - 检测到开源模型冒充 -> 封顶 20 分
    """

    name = "model_consistency"
    category = CATEGORIES["model_consistency"]
    weight = WEIGHTS["model_consistency"]
    modes = ["quick", "standard", "full"]
    timeout = 45  # v2.7: 3次请求需要更多时间
    estimated_tokens = 600  # v2.7: 3 次请求 × ~200 tokens

    # v2.7: 创意写作问题
    QUESTION = HAIKU_QUESTION

    def run(self, client) -> CheckResultV2:
        responses_raw = []
        content_list: list[str] = []
        total_tokens = 0
        errors: list[str] = []

        # v2.7: 3 次相同请求（替代之前3次不同数学题）
        for i in range(3):
            resp = client.chat(
                messages=[{"role": "user", "content": self.QUESTION}],
                max_tokens=60,
                temperature=0.0,
                detector_name=self.name,
            )
            if resp.success:
                responses_raw.append(resp)
                content_list.append((resp.content or "").strip())
                if resp.usage:
                    total_tokens += resp.usage.total_tokens
            else:
                errors.append(f"第{i+1}次请求失败: {resp.error}")

        # 错误处理
        if len(responses_raw) < 2:
            return create_error_result(
                detector=self,
                error_type=ErrorScore.REQUEST_FAILED,
                details=f"请求失败: {'; '.join(errors)}",
                cost_tokens=total_tokens,
                custom_message=f"模型一致性检测请求失败: {'; '.join(errors[:2])}",
            )

        # === v2.7: 三维度内容评分 ===
        final_score, c_score, f_score, s_score = score_responses(content_list)

        # === 模型名一致性检查（OpenAI 协议特有） ===
        model_issues: list[Issue] = []
        models = [(r.model or "").lower() for r in responses_raw]
        claimed = client.model.lower()

        norm_models = [normalize_model_name(m) for m in models]
        norm_claimed = normalize_model_name(claimed)
        unique_norm = set(norm_models)

        model_penalty = 0.0
        model_capped = False
        model_cap = 100.0

        if len(unique_norm) == 1:
            # 模型名一致
            norm_model = norm_models[0]
            if norm_model == norm_claimed:
                # 完全匹配，无惩罚
                pass
            elif norm_claimed in norm_model or norm_model in norm_claimed:
                # 基本匹配，轻微惩罚
                model_penalty = 5.0
                model_issues.append(Issue(
                    level=IssueLevel.MINOR,
                    message=f"模型名基本匹配但略有差异: 声称 {client.model}, 实际 {responses_raw[0].model}",
                    detector_name=self.name,
                ))
            else:
                # 检查假模型
                for pattern in FAKE_MODEL_PATTERNS:
                    if pattern in models[0]:
                        model_capped = True
                        model_cap = 15.0
                        model_issues.append(Issue(
                            level=IssueLevel.CRITICAL,
                            message=f"检测到假模型模式 '{pattern}': {responses_raw[0].model}",
                            detector_name=self.name,
                        ))
                        break

                if not model_capped:
                    # 检查开源模型冒充
                    for oss in KNOWN_OPEN_SOURCE_MODELS:
                        if oss in models[0]:
                            model_capped = True
                            model_cap = 20.0
                            model_issues.append(Issue(
                                level=IssueLevel.CRITICAL,
                                message=f"响应指向开源模型 '{oss}': {responses_raw[0].model}",
                                detector_name=self.name,
                            ))
                            break

                if not model_capped:
                    # 检查是否是真实 OpenAI 模型但版本不同
                    is_real = False
                    for real in REAL_OPENAI_MODELS:
                        if real.lower() in models[0]:
                            model_penalty = 10.0
                            model_issues.append(Issue(
                                level=IssueLevel.MINOR,
                                message=f"响应为真实 OpenAI 模型但版本不同: {responses_raw[0].model}",
                                detector_name=self.name,
                            ))
                            is_real = True
                            break

                    if not is_real:
                        model_penalty = 15.0
                        model_issues.append(Issue(
                            level=IssueLevel.MAJOR,
                            message=f"model 字段不匹配: 声称 {client.model}, 实际 {responses_raw[0].model}",
                            detector_name=self.name,
                        ))
        else:
            # 模型名不一致
            model_penalty = 30.0
            model_issues.append(Issue(
                level=IssueLevel.MAJOR,
                message=f"多次请求 model 字段不一致: {list(set(models))}",
                detector_name=self.name,
            ))

        # 应用模型名修饰符
        if model_capped:
            final_score = min(final_score, model_cap)
        else:
            final_score = max(0, final_score - model_penalty)

        # 置信度
        confidence, confidence_reason = calc_confidence(content_list, final_score)
        # 如果模型名有问题，降低置信度
        if model_penalty >= 15 or model_capped:
            confidence = min(confidence, 0.75)
            confidence_reason += "；模型名检查存在异常"

        # 合并 issues
        content_issues = generate_issues(
            content_list, c_score, f_score, s_score, self.name
        )
        all_issues = content_issues + model_issues

        status = "pass" if final_score >= 50 else "fail"

        details = (
            f"3次请求 | "
            f"内容评分: 一致性={c_score:.0f}(40%) "
            f"特征={f_score:.0f}(30%) "
            f"语义={s_score:.0f}(30%) "
            f"模型名: {'一致' if len(unique_norm)==1 else '不一致'} "
            f"惩罚={model_penalty:.0f}"
            f"{' [封顶'+str(int(model_cap))+']' if model_capped else ''} "
            f"=> 总分={final_score}"
        )

        return CheckResultV2(
            name=self.name,
            category=self.category,
            score=final_score,
            weight=self.weight,
            status=status,
            cost_tokens=total_tokens,
            confidence=confidence,
            confidence_reason=confidence_reason,
            details=details,
            issues=all_issues,
        )
