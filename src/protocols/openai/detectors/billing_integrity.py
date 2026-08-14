"""
billing_integrity - 计费完整性检测（OpenAI 协议，v2.7 合并版）

核心变更（2026-08-14）：
  - 合并 token_billing 的核心检查逻辑（completion_tokens 合理性）
  - 降低 max_tokens 从 100 → 60，减少 output token 消耗
  - 保持 v2.6 的范围检查策略，避免误报

检测逻辑：
  1. Input token 范围检查（基于观察数据）
  2. Cache 字段审计
  3. Output token 合理性检查（从 token_billing 移植）
  4. Total 一致性检查（prompt + completion ≈ total）

注意：本检测器仅检查数据合理性，不做诚信判定。
"""

from src.core.detector_base import ActiveDetector
from src.core.models import CheckResultV2, Issue, IssueLevel
from ..config import WEIGHTS, CATEGORIES
from src.utils.token_counter import count_tokens

# ─── 已知 Prompt ───────────────────────────────────────────────
_KNOWN_PROMPT = "Write a haiku about artificial intelligence in exactly three lines."

# 纯文本字符数（用于估算）
_PROMPT_CHARS = len(_KNOWN_PROMPT)

# 基于 OpenAI 官方 API 的观察数据（2026-08-11）：
# - 纯文本 token 数：~15
# - 包含消息格式后：~19
# - 中转站通常添加系统消息后的实际范围：30~150 tokens
# 
# 因此：
# - < 30：偏低（可能用了不同的计算方式）
# - 30~200：正常范围（包含系统消息开销）
# - 200~500：偏高（可能包含较多工具定义）
# - > 500：显著异常（可能存在问题）

# 最小合理值（纯文本 + 基本格式）
_MIN_REASONABLE = 15

# 正常范围上限（包含系统消息、工具定义等合理开销）
_NORMAL_RANGE_MAX = 200

# 警告阈值（超过此值才提示）
_WARNING_THRESHOLD = 500


class BillingIntegrityDetector(ActiveDetector):
    """
    计费完整性检测器（v2.6 重构版）
    
    核心逻辑：
      - 接受中转站必然有系统开销的事实
      - 用宽松的范围检查替代严格的倍数检查
      - 仅对极端异常情况进行提示
    
    评分：
      - 数据完整 → 90-100
      - 正常范围 → 85-95
      - 偏高但可接受 → 80-90
      - 极端异常 → 60-80
      - 请求失败 → 0
    """

    name = "billing_integrity"
    category = CATEGORIES["billing_integrity"]
    weight = WEIGHTS["billing_integrity"]
    modes = ["standard", "full"]
    timeout = 15
    estimated_tokens = 1500  # v2.7: 降低预估（max_tokens 从 100 降到 60）

    def run(self, client) -> CheckResultV2:
        issues: list[Issue] = []
        score = 95  # 默认高分，仅极端情况扣分

        # ── 发送基准请求 ──────────────────────────────────────
        resp = client.chat(
            messages=[{"role": "user", "content": _KNOWN_PROMPT}],
            max_tokens=60,  # v2.7: 从 100 降到 60，减少 output token
            detector_name=self.name,
        )

        if not resp.success:
            return CheckResultV2(
                name=self.name, category=self.category, score=0, weight=self.weight,
                status="error", cost_tokens=0,
                details=f"请求失败: {resp.error}",
                issues=[Issue(level=IssueLevel.MAJOR, message=f"计费检测请求失败: {resp.error}", detector_name=self.name)],
            )

        usage = resp.usage
        if not usage:
            return CheckResultV2(
                name=self.name, category=self.category, score=0, weight=self.weight,
                status="error", cost_tokens=0,
                details="usage 字段完全缺失",
                issues=[Issue(level=IssueLevel.CRITICAL, message="usage 字段完全缺失，无法进行计费审计", detector_name=self.name)],
            )

        reported_input = usage.prompt_tokens
        reported_output = usage.completion_tokens
        reported_total = usage.total_tokens

        # 构建详情
        details_parts = [
            f"prompt={reported_input}",
            f"completion={reported_output}",
            f"total={reported_total}",
        ]

        # ── 1. Input Token 合理性检查 ─────────────────────────
        # v2.6: 基于观察数据的宽松范围检查
        
        if reported_input < _MIN_REASONABLE:
            # 低于最小合理值（很少见）
            score -= 5
            issues.append(Issue(
                level=IssueLevel.MINOR,
                message=f"prompt_tokens ({reported_input}) 低于常规值，可能使用了特殊的 token 计算方式",
                detector_name=self.name,
            ))
        elif reported_input <= _NORMAL_RANGE_MAX:
            # 正常范围（绝大多数中转站）
            issues.append(Issue(
                level=IssueLevel.OK,
                message=f"prompt_tokens ({reported_input}) 在正常范围内（包含系统消息等开销）",
                detector_name=self.name,
            ))
        elif reported_input <= _WARNING_THRESHOLD:
            # 偏高但可接受（可能包含较多工具定义）
            score -= 5
            issues.append(Issue(
                level=IssueLevel.MINOR,
                message=f"prompt_tokens ({reported_input}) 偏高，可能包含较多工具定义或系统消息",
                detector_name=self.name,
            ))
        else:
            # 显著异常（>500）
            score -= 15
            issues.append(Issue(
                level=IssueLevel.MAJOR,
                message=f"prompt_tokens ({reported_input}) 显著高于常规值，建议检查具体计费明细",
                detector_name=self.name,
            ))

        # ── 2. Cache 字段审计 ────────────────────────────────
        cache_read = getattr(usage, 'cache_read_tokens', 0) or 0
        cache_creation = getattr(usage, 'cache_creation_tokens', 0) or 0
        has_cache = cache_read > 0 or cache_creation > 0

        if has_cache:
            details_parts.append(f"cache_read={cache_read}")
            details_parts.append(f"cache_creation={cache_creation}")
            # 非缓存请求返回 cache 字段是明确的异常
            score -= 20
            issues.append(Issue(
                level=IssueLevel.MAJOR,
                message=f"非缓存请求返回 cache 字段（read={cache_read}, creation={cache_creation}）",
                detector_name=self.name,
            ))
        else:
            details_parts.append("cache=无")
            issues.append(Issue(
                level=IssueLevel.OK,
                message="cache 字段正常",
                detector_name=self.name,
            ))

        # ── 3. 输出 token 合理性检查（v2.7: 从 token_billing 合并） ───
        content = resp.content or ""
        estimated_output_tokens = count_tokens(content)

        if reported_output == 0:
            score -= 10
            issues.append(Issue(
                level=IssueLevel.MINOR,
                message="completion_tokens 为 0，可能响应为空",
                detector_name=self.name,
            ))
        elif estimated_output_tokens > 0 and reported_output < estimated_output_tokens * 0.3:
            # 实际 token 远少于估算，可能虚报
            score -= 15
            issues.append(Issue(
                level=IssueLevel.MAJOR,
                message=f"completion_tokens ({reported_output}) 远少于估算 ({estimated_output_tokens})，可能虚报",
                detector_name=self.name,
            ))
            details_parts.append(f"output_low={reported_output}<{estimated_output_tokens}")
        elif estimated_output_tokens > 0 and reported_output > estimated_output_tokens * 5:
            # 实际 token 远多于估算，仅提示
            issues.append(Issue(
                level=IssueLevel.MINOR,
                message=f"completion_tokens ({reported_output}) 远多于估算 ({estimated_output_tokens})",
                detector_name=self.name,
            ))
            details_parts.append(f"output_high={reported_output}>{estimated_output_tokens}")
        else:
            details_parts.append(f"output_ok={reported_output}")
            issues.append(Issue(
                level=IssueLevel.OK,
                message=f"completion_tokens ({reported_output}) 正常",
                detector_name=self.name,
            ))

        # ── 4. Total 一致性检查 ──────────────────────────────
        # 检查 total_tokens 是否约等于 prompt + completion
        expected_total = reported_input + reported_output
        if abs(reported_total - expected_total) > 5:  # 允许 5 token 误差
            details_parts.append(f"total_mismatch={reported_total}!={expected_total}")
            score -= 10
            issues.append(Issue(
                level=IssueLevel.MINOR,
                message=f"total_tokens ({reported_total}) 与 prompt+completion ({expected_total}) 不一致",
                detector_name=self.name,
            ))
        else:
            details_parts.append("total_consistent")
            issues.append(Issue(
                level=IssueLevel.OK,
                message="token 计数一致性正常",
                detector_name=self.name,
            ))

        # 钳制分数
        score = max(0, min(100, score))

        return CheckResultV2(
            name=self.name, category=self.category, score=score, weight=self.weight,
            cost_tokens=usage.total_tokens if usage else 0,
            details=" | ".join(details_parts),
            issues=issues,
        )
