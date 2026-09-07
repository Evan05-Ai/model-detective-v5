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

        # v3.0.4: 提前提取缓存字段，供固定开销披露与 Cache 审计共用
        cache_create = usage.cache_creation_input_tokens
        cache_read = usage.cache_read_input_tokens

        # v3.0.4: 单请求固定开销披露（计费公平性发现），按缓存字段分型。
        # 我方 prompt 仅 ~19 tokens；上报 input 与估算的差额即中转站注入的
        # 固定开销。开销构成决定真实计费：
        #   - cache_read 型（上游系统提示走缓存）：官方计费仅 0.1x，成本影响小
        #   - plain/cache_creation 型：按全价/1.25x 计费，成本影响大
        fixed_overhead = reported_input - estimated_input
        if fixed_overhead > 1000:
            overhead_parts = []
            if cache_create > 0:
                overhead_parts.append(f"缓存写入 {cache_create}（官方计费 1.25x）")
            if cache_read > 0:
                overhead_parts.append(f"缓存读取 {cache_read}（官方计费仅 0.1x）")
            plain_overhead = fixed_overhead - cache_create - cache_read
            if plain_overhead > 0:
                overhead_parts.append(f"非缓存注入 {plain_overhead}（按全价计费）")
            composition = "；".join(overhead_parts) or "按全价计费"
            # 全价当量 = 用户按官方价"实际承受"的输入成本
            equiv = cache_create * 1.25 + cache_read * 0.1 + max(0, plain_overhead)
            issues.append(Issue(
                level=IssueLevel.OK,
                message=(
                    f"计费公平性提示：我方本次请求仅约 {estimated_input} tokens，"
                    f"但该站上报输入 {reported_input} tokens——单请求固定开销 ≈{fixed_overhead} "
                    f"tokens（{composition}），全价当量 ≈{int(equiv)} tokens/请求。"
                    f"该开销会计入你的每一次对话，长期使用成本需按倍率自行评估。"
                ),
                detector_name=self.name,
            ))

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
        # v3.0.4: 固定开销披露已覆盖大额注入场景（同一事实不重复扣分）；
        # 偏差扣分改用绝对量门槛，避免小分母（19 tokens）放大无意义百分比
        input_delta = reported_input - estimated_input
        if fixed_overhead > 1000:
            issues.append(Issue(
                level=IssueLevel.MINOR,
                message=f"input_tokens 显著高于估算（上报 {reported_input}，估算约 {estimated_input}），"
                        f"详见上方固定开销披露（已计入披露，不重复扣分）",
                detector_name=self.name,
            ))
        elif input_delta > 200 and abs(input_deviation) > 100:
            score -= 25
            issues.append(Issue(
                level=IssueLevel.MINOR,
                message=f"input_tokens 显著高于估算（上报 {reported_input}，估算约 {estimated_input}，多出 {input_delta}）。可能原因：中转站包含系统消息、使用不同 tokenizer、或存在额外开销",
                detector_name=self.name,
            ))
        elif input_delta > 100 and abs(input_deviation) > 50:
            score -= 10
            issues.append(Issue(
                level=IssueLevel.MINOR,
                message=f"input_tokens 高于估算（上报 {reported_input}，估算约 {estimated_input}，多出 {input_delta}）。中转站可能有额外 token 开销",
                detector_name=self.name,
            ))
        else:
            issues.append(Issue(
                level=IssueLevel.OK,
                message=f"input_tokens 在合理范围内（上报 {reported_input}，估算约 {estimated_input}，偏差 {input_deviation:+.1f}%）",
                detector_name=self.name,
            ))

        # ── 2. Cache 字段审计（字段已在第 1 步前提取）────────────
        has_cache = cache_create > 0 or cache_read > 0

        if has_cache:
            precision_detail_parts.append(f"cache_create={cache_create}")
            precision_detail_parts.append(f"cache_read={cache_read}")
            # v3.0.4: 区分两种场景，避免与固定开销披露自相矛盾：
            #   a) 缓存字段本身成规模（≥1000 tokens，如神秘cc input≈cache_read
            #      47.9k、Kiro 类 input 小但 read 45k）→ 上游带缓存系统提示的
            #      透传，字段有来源，不判"可能虚报"
            #   b) input 小且 cache 字段也微小/无来源 → 才可疑
            coherent_with_overhead = (cache_create + cache_read) >= 1000
            if coherent_with_overhead:
                issues.append(Issue(
                    level=IssueLevel.OK,
                    message=f"cache 字段与固定开销相干（read={cache_read}, create={cache_create}），"
                            f"为上游系统提示走缓存的特征，非缓存计费造假",
                    detector_name=self.name,
                ))
            else:
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
            # v3.0.4: 小分母护栏——估算 <20 tokens 时百分比噪声过大，只披露不扣分
            if estimated_output < 20:
                issues.append(Issue(
                    level=IssueLevel.OK,
                    message=f"output_tokens 上报 {reported_output}（估算基数过小，百分比无统计意义，不扣分）",
                    detector_name=self.name,
                ))
            elif abs(output_deviation) > 100:
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
            # v3.0.4: 纯披露不扣分——倍率大小由固定开销披露解释，倍率本身
            # 不衡量"多收你多少钱"（真实费用 = 官方价 × 上报 × 倍率系数）
            issues.append(Issue(
                level=IssueLevel.MINOR,
                message=f"上报/估算比值 {multiplier:.1f}x（仅披露不扣分）。注意：估算仅供参考，"
                        f"中转站可能包含系统消息、工具调用等额外 token",
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
