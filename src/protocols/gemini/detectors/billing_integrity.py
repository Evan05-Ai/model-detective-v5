"""
billing_integrity - 计费完整性检测（合规，v2.2 新增）

Gemini 协议版本：验证 promptTokenCount/candidatesTokenCount 精度 + 计费倍率

依赖：tiktoken（可选，缺失时回退到 len//4 粗略估算）
"""

from src.core.detector_base import ActiveDetector
from src.core.models import CheckResultV2, Issue, IssueLevel
from ..config import WEIGHTS, CATEGORIES
from src.utils.token_counter import count_tokens, _HAS_TIKTOKEN, ANTHROPIC_MESSAGE_OVERHEAD as _MESSAGE_FORMAT_OVERHEAD

_KNOWN_PROMPT = "Write a haiku about artificial intelligence in exactly three lines."

# Gemini generateContent 的 promptTokenCount 包含 contents 结构 token，约 5 token 开销
_KNOWN_PROMPT_TOKENS = (count_tokens(_KNOWN_PROMPT) + _MESSAGE_FORMAT_OVERHEAD) if _HAS_TIKTOKEN else None


class BillingIntegrityDetector(ActiveDetector):
    """计费完整性检测器（Gemini 协议，v2.2）"""

    name = "billing_integrity"
    category = CATEGORIES["billing_integrity"]
    weight = WEIGHTS["billing_integrity"]
    modes = ["standard", "full"]
    timeout = 15
    estimated_tokens = 2000  # v2.5: 设置合理预估，实际消耗约 1500-2000 tokens

    def run(self, client) -> CheckResultV2:
        issues: list[Issue] = []
        score = 100

        resp = client.generate(
            contents=[{"role": "user", "parts": [{"text": _KNOWN_PROMPT}]}],
            max_tokens=100,
            detector_name=self.name,
        )

        if not resp.success:
            return CheckResultV2(
                name=self.name, category=self.category, score=0, weight=self.weight,
                status="error", cost_tokens=0,
                details=f"request failed: {resp.error}",
                issues=[Issue(level=IssueLevel.MAJOR, message=f"billing check failed: {resp.error}", detector_name=self.name)],
            )

        usage = resp.usage
        if not usage:
            return CheckResultV2(
                name=self.name, category=self.category, score=0, weight=self.weight,
                status="error", cost_tokens=0,
                details="usageMetadata missing",
                issues=[Issue(level=IssueLevel.CRITICAL, message="usageMetadata missing, cannot audit billing", detector_name=self.name)],
            )

        # -- 1. Tokenizer precision check --
        reported_input = usage.prompt_tokens
        if _HAS_TIKTOKEN and _KNOWN_PROMPT_TOKENS:
            actual_input = _KNOWN_PROMPT_TOKENS
        else:
            actual_input = count_tokens(_KNOWN_PROMPT) + _MESSAGE_FORMAT_OVERHEAD
        input_deviation = (reported_input - actual_input) / max(actual_input, 1) * 100

        precision_parts = [
            f"reported_input={reported_input}",
            f"estimated_input={actual_input}",
            f"overhead={_MESSAGE_FORMAT_OVERHEAD}",
            f"deviation={input_deviation:+.1f}%",
            f"tokenizer={'tiktoken' if _HAS_TIKTOKEN else 'chars/4'}",
        ]

        if abs(input_deviation) > 30:
            score -= 40
            issues.append(Issue(level=IssueLevel.MAJOR,
                message=f"promptTokenCount deviation {input_deviation:+.0f}%! reported {reported_input}, estimated {actual_input}",
                detector_name=self.name))
        elif abs(input_deviation) > 10:
            score -= 20
            issues.append(Issue(level=IssueLevel.MINOR,
                message=f"promptTokenCount deviation {input_deviation:+.0f}% (reported {reported_input})",
                detector_name=self.name))
        else:
            issues.append(Issue(level=IssueLevel.OK,
                message=f"promptTokenCount precision OK (deviation {input_deviation:+.1f}%)",
                detector_name=self.name))

        # -- 2. Output token precision --
        reported_output = usage.completion_tokens
        content = resp.content or ""
        estimated_output = count_tokens(content)
        if estimated_output > 0:
            output_deviation = (reported_output - estimated_output) / estimated_output * 100
            precision_parts.append(f"reported_output={reported_output}")
            precision_parts.append(f"estimated_output={estimated_output}")
            precision_parts.append(f"output_deviation={output_deviation:+.1f}%")
            if abs(output_deviation) > 50:
                score -= 20
                issues.append(Issue(level=IssueLevel.MAJOR,
                    message=f"candidatesTokenCount deviation {output_deviation:+.0f}%", detector_name=self.name))
            elif abs(output_deviation) > 20:
                score -= 15
                issues.append(Issue(level=IssueLevel.MINOR,
                    message=f"candidatesTokenCount deviation {output_deviation:+.0f}%", detector_name=self.name))

        # -- 3. Billing multiplier --
        estimated_total = actual_input + estimated_output
        reported_total = reported_input + reported_output
        multiplier = reported_total / max(estimated_total, 1)
        precision_parts.append(f"multiplier={multiplier:.2f}x")
        precision_parts.append(f"reported_total={reported_total}")
        precision_parts.append(f"estimated_total={estimated_total}")

        if multiplier > 2.0:
            score -= 20
            issues.append(Issue(level=IssueLevel.CRITICAL,
                message=f"billing multiplier {multiplier:.1f}x! severe inflation",
                detector_name=self.name))
        elif multiplier > 1.5:
            score -= 10
            issues.append(Issue(level=IssueLevel.MAJOR,
                message=f"billing multiplier {multiplier:.1f}x, significant inflation",
                detector_name=self.name))
        elif multiplier > 1.2:
            issues.append(Issue(level=IssueLevel.MINOR,
                message=f"billing multiplier {multiplier:.1f}x, slight inflation",
                detector_name=self.name))
        else:
            issues.append(Issue(level=IssueLevel.OK,
                message=f"billing multiplier {multiplier:.2f}x, billing transparency OK",
                detector_name=self.name))

        score = max(0, min(100, score))
        return CheckResultV2(
            name=self.name, category=self.category, score=score, weight=self.weight,
            cost_tokens=usage.total_tokens if usage else 0,
            details=" | ".join(precision_parts),
            issues=issues,
        )
