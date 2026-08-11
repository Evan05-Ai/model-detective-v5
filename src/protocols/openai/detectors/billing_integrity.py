"""
billing_integrity - 计费完整性检测（OpenAI 协议，v2.5 修正版）

检测项：
  1. Token 计数合理性检查 — 验证上报的 token 数是否在合理范围内
  2. Cache 字段审计 — 检查 cache 相关字段存在性
  3. 输出 token 合理性 — 估算 output tokens 对比上报值（宽松阈值）
  4. 计费倍率参考 — 计算上报/估算比值，仅作参考不直接判定

v2.5 重要修正（2026-08-11）：
  - 同步 Anthropic 版本的宽松阈值策略
  - 不再声称用 tiktoken "精确"计算（中转站可能有额外开销）
  - 放宽偏差阈值：input >200% 才提示，避免误报
  - 放宽倍率阈值：>5x 才提示，不作为负面评分
  - 移除"虚报计费"等主观定性，改为客观数据展示
  - 增加常见原因说明：系统消息、工具定义、不同 tokenizer 等

注意：本检测器仅检查数据合理性，不做诚信判定。
"""

from src.core.detector_base import ActiveDetector
from src.core.models import CheckResultV2, Issue, IssueLevel
from ..config import WEIGHTS, CATEGORIES

# ─── Token 估算（仅供参考，非精确值）────────────────────────────
def _estimate_tokens(text: str) -> int:
    """
    粗略估算 token 数。注意：这只是估算！
    
    中转站可能使用：
    - OpenAI 官方 tiktoken
    - 近似估算（字符数/4）
    - 包含系统消息、工具定义等额外 token
    
    因此估算值与上报值存在偏差是正常的，不应直接判定为"欺诈"。
    """
    # 保守估算：1 token ≈ 4 字符（OpenAI 通常以此估算）
    return max(1, int(len(text) / 4))


# ─── 已知的精确 prompt（用于 token 估算参考）────────────────────
_KNOWN_PROMPT = "Write a haiku about artificial intelligence in exactly three lines."

# 估算参考值（非精确值！）
_ESTIMATED_PROMPT_TOKENS = _estimate_tokens(_KNOWN_PROMPT)


class BillingIntegrityDetector(ActiveDetector):
    """
    计费完整性检测器（OpenAI 协议，v2.5 修正版）

    评分逻辑（宽松）：
      - 数据完整且合理 → 90-100
      - 轻微偏差（<200%）→ 80-90
      - 显著偏差（200-500%）→ 60-80（提示可能原因，不扣分）
      - 极端偏差（>500%）或 cache 异常 → 40-60
      - 请求失败 → 0
    
    重要：本检测器不做"诚信"判定，仅做数据合理性检查。
    """

    name = "billing_integrity"
    category = CATEGORIES["billing_integrity"]
    weight = WEIGHTS["billing_integrity"]
    modes = ["standard", "full"]
    timeout = 15
    estimated_tokens = 2000

    def run(self, client) -> CheckResultV2:
        issues: list[Issue] = []
        score = 100

        # ── 发送基准请求 ──────────────────────────────────────
        resp = client.chat(
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
        estimated_input = _ESTIMATED_PROMPT_TOKENS
        
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

        # v2.5: 大幅放宽阈值，避免误报 GPT 中转站
        # GPT 中转站常见情况：
        # - 添加系统消息：+10~50 tokens
        # - 工具定义开销：+50~200 tokens
        # - 不同 tokenizer：±20% 偏差
        if reported_input > estimated_input * 5:  # 超过 5 倍才认为是显著异常
            score -= 20
            issues.append(Issue(
                level=IssueLevel.MINOR,
                message=f"input_tokens 显著高于估算（上报 {reported_input}，估算约 {estimated_input}）。常见原因：中转站添加了系统消息、包含工具定义、或使用不同计算方式",
                detector_name=self.name,
            ))
        elif reported_input > estimated_input * 2:  # 2-5 倍给予提示，不扣分
            # 不扣分，仅提示
            issues.append(Issue(
                level=IssueLevel.OK,  # 用 OK 级别，不告警
                message=f"input_tokens 高于估算（上报 {reported_input}，估算约 {estimated_input}，偏差 {input_deviation:+.0f}%）。可能包含系统消息或额外开销",
                detector_name=self.name,
            ))
        else:
            issues.append(Issue(
                level=IssueLevel.OK,
                message=f"input_tokens 在合理范围内（上报 {reported_input}，估算约 {estimated_input}，偏差 {input_deviation:+.1f}%）",
                detector_name=self.name,
            ))

        # ── 2. Cache 字段审计 ────────────────────────────────
        # OpenAI 格式：prompt_tokens_details.cache_read_tokens / cache_creation_tokens
        cache_read = getattr(usage, 'cache_read_tokens', 0) or 0
        cache_creation = getattr(usage, 'cache_creation_tokens', 0) or 0
        has_cache = cache_read > 0 or cache_creation > 0

        if has_cache:
            precision_detail_parts.append(f"cache_read={cache_read}")
            precision_detail_parts.append(f"cache_creation={cache_creation}")

            # 本次请求未启用缓存，但 API 返回了 cache 字段 → 可能虚报
            issues.append(Issue(
                level=IssueLevel.MAJOR,
                message=f"非缓存请求却返回 cache 字段（read={cache_read}, creation={cache_creation}），可能虚报缓存计费",
                detector_name=self.name,
            ))
            score -= 30
        else:
            precision_detail_parts.append("cache=无")
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

            # v2.5: 大幅放宽 output 阈值（生成长度难以预估）
            if abs(output_deviation) > 200:  # 超过 200% 才提示
                # 不扣分，仅提示
                issues.append(Issue(
                    level=IssueLevel.OK,
                    message=f"output_tokens 高于估算（上报 {reported_output}，估算约 {estimated_output}）。可能包含停止 token 或其他开销",
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

        # 仅作为参考信息，大幅放宽阈值到 5x
        if multiplier > 5.0:
            # 超过 5 倍才提示，且不作为负面评分
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
