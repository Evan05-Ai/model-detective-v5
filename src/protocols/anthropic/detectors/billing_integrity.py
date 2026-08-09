"""
billing_integrity - 计费完整性检测（合规，v2.5 修正版）

检测项：
  1. Token 计数合理性检查 — 验证上报的 token 数是否在合理范围内
  2. Cache 字段审计 — 检查 cache_creation/cache_read 字段存在性
  3. 输出 token 合理性 — 估算 output tokens 对比上报值（宽松阈值）
  4. 计费倍率参考 — 计算上报/估算比值，仅作参考不直接判定欺诈

v2.5 重要修正：
  - 不再声称用 tiktoken "精确"计算 Claude token（Claude 使用不同 tokenizer）
  - 放宽偏差阈值，避免误报
  - 移除"虚报计费"等主观定性，改为客观数据展示
  - 增加免责声明：中转站可能使用不同 token 计算方式
"""

import re
from src.core.detector_base import ActiveDetector
from src.core.models import CheckResultV2, Issue, IssueLevel
from ..config import WEIGHTS, CATEGORIES

# ─── Token 估算（仅供参考，非精确值）────────────────────────────
def _estimate_tokens(text: str) -> int:
    """
    粗略估算 token 数。注意：这只是估算！
    
    Claude 实际使用的 tokenizer 与 GPT 不同，且中转站可能：
    - 使用 Anthropic 官方 tokenizer
    - 使用近似估算
    - 包含系统消息、工具定义等额外 token
    
    因此估算值与上报值存在偏差是正常的，不应直接判定为"欺诈"。
    """
    # 保守估算：1 token ≈ 3.5 字符（Claude 通常比 GPT 更"高效"）
    return max(1, int(len(text) / 3.5))


# ─── 已知的精确 prompt（用于 token 估算参考）────────────────────
_KNOWN_PROMPT = "Write a haiku about artificial intelligence in exactly three lines."

# 估算参考值（非精确值！）
_ESTIMATED_PROMPT_TOKENS = _estimate_tokens(_KNOWN_PROMPT)


class BillingIntegrityDetector(ActiveDetector):
    """
    计费完整性检测器（v2.2）

    评分逻辑：
      - 精度校验通过 + 无异常 → 90-100
      - 精度偏差 10-30% → 60-80
      - 精度偏差 >30% 或 cache 虚报 → 30-50
      - 请求失败 → 0
    """

    name = "billing_integrity"
    category = CATEGORIES["billing_integrity"]
    weight = WEIGHTS["billing_integrity"]
    modes = ["standard", "full"]
    timeout = 15
    estimated_tokens = 2000  # v2.5: 设置合理预估，实际消耗约 1500-2000 tokens

    def run(self, client) -> CheckResultV2:
        issues: list[Issue] = []
        score = 100

        # ── 发送基准请求 ──────────────────────────────────────
        resp = client.messages(
            messages=[{"role": "user", "content": _KNOWN_PROMPT}],
            max_tokens=100,
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

        # ── 1. Input Token 合理性检查 ─────────────────────────
        reported_input = usage.prompt_tokens
        estimated_input = _estimate_tokens(_KNOWN_PROMPT)
        
        # 计算偏差（仅作参考）
        if estimated_input > 0:
            input_deviation = (reported_input - estimated_input) / estimated_input * 100
        else:
            input_deviation = 0

        # 构建详情（客观描述，不主观定性）
        precision_detail_parts = [
            f"reported_input={reported_input}",
            f"estimated_input={estimated_input}",
            f"deviation={input_deviation:+.1f}%",
            f"note=estimate_only",
        ]

        # v2.5: 放宽阈值，避免误报
        # 注意：中转站可能包含系统消息、工具定义等额外 token
        if abs(input_deviation) > 100:  # 偏差超过 100% 才认为是异常
            score -= 25
            issues.append(Issue(
                level=IssueLevel.MINOR,
                message=f"input_tokens 显著高于估算（上报 {reported_input}，估算约 {estimated_input}）。可能原因：中转站包含系统消息、使用不同 tokenizer、或存在额外开销",
                detector_name=self.name,
            ))
        elif abs(input_deviation) > 50:  # 偏差 50-100% 给予提示
            score -= 10
            issues.append(Issue(
                level=IssueLevel.MINOR,
                message=f"input_tokens 高于估算（上报 {reported_input}，估算约 {estimated_input}）。中转站可能有额外 token 开销",
                detector_name=self.name,
            ))
        else:
            issues.append(Issue(
                level=IssueLevel.OK,
                message=f"input_tokens 在合理范围内（上报 {reported_input}，估算约 {estimated_input}，偏差 {input_deviation:+.1f}%）",
                detector_name=self.name,
            ))

        # ── 2. Cache 字段审计 ────────────────────────────────
        cache_create = usage.cache_creation_input_tokens
        cache_read = usage.cache_read_input_tokens
        has_cache = cache_create > 0 or cache_read > 0

        if has_cache:
            precision_detail_parts.append(f"cache_create={cache_create}")
            precision_detail_parts.append(f"cache_read={cache_read}")

            # 本次请求未启用缓存，但 API 返回了 cache 字段 → 可能虚报
            issues.append(Issue(
                level=IssueLevel.MAJOR,
                message=f"非缓存请求却返回 cache 字段（creation={cache_create}, read={cache_read}），可能虚报缓存计费",
                detector_name=self.name,
            ))
            score -= 30
        else:
            precision_detail_parts.append("cache=无")
            # 正常：无缓存请求不应有 cache 字段
            issues.append(Issue(
                level=IssueLevel.OK,
                message="未检测到异常 cache 计费字段",
                detector_name=self.name,
            ))

        # ── 3. 输出 token 合理性检查 ─────────────────────────
        reported_output = usage.completion_tokens
        content = resp.content or ""
        estimated_output = _estimate_tokens(content)

        output_deviation = 0.0
        if estimated_output > 0:
            output_deviation = (reported_output - estimated_output) / estimated_output * 100
            precision_detail_parts.append(f"reported_output={reported_output}")
            precision_detail_parts.append(f"estimated_output={estimated_output}")
            precision_detail_parts.append(f"output_deviation={output_deviation:+.1f}%")

            # v2.5: 放宽阈值，output token 更难准确估算（取决于生成长度）
            if abs(output_deviation) > 100:
                score -= 15
                issues.append(Issue(
                    level=IssueLevel.MINOR,
                    message=f"output_tokens 显著高于估算（上报 {reported_output}，估算约 {estimated_output}）。可能包含停止 token 或其他开销",
                    detector_name=self.name,
                ))
            elif abs(output_deviation) > 50:
                score -= 5
                issues.append(Issue(
                    level=IssueLevel.MINOR,
                    message=f"output_tokens 高于估算（上报 {reported_output}，估算约 {estimated_output}）",
                    detector_name=self.name,
                ))
        else:
            precision_detail_parts.append("response_empty")

        # ── 4. 计费倍率参考（仅作参考，不直接判定）────────────────
        # v2.5: 明确说明这只是参考值，不应作为"欺诈"证据
        estimated_total = estimated_input + estimated_output
        reported_total = reported_input + reported_output
        multiplier = reported_total / max(estimated_total, 1)

        precision_detail_parts.append(f"ratio={multiplier:.2f}x")
        precision_detail_parts.append(f"reported_total={reported_total}")
        precision_detail_parts.append(f"estimated_total={estimated_total}")

        # 仅作为参考信息，大幅放宽阈值
        if multiplier > 3.0:
            # 超过 3 倍才提示，且不作为负面评分
            issues.append(Issue(
                level=IssueLevel.MINOR,
                message=f"上报/估算比值 {multiplier:.1f}x。注意：估算仅供参考，中转站可能包含系统消息、工具调用等额外 token",
                detector_name=self.name,
            ))
        else:
            issues.append(Issue(
                level=IssueLevel.OK,
                message=f"上报/估算比值 {multiplier:.2f}x（上报 {reported_total}，估算约 {estimated_total}）",
                detector_name=self.name,
            ))

        # 钳制分数
        score = max(0, min(100, score))

        return CheckResultV2(
            name=self.name, category=self.category, score=score, weight=self.weight,
            cost_tokens=usage.total_tokens if usage else 0,
            details=" | ".join(precision_detail_parts),
            issues=issues,
        )
