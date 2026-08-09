"""
billing_integrity - 计费完整性检测（合规，v2.2 新增）

OpenAI 协议版本：验证 prompt_tokens/completion_tokens 精度 + cache 字段审计 + 计费倍率

依赖：tiktoken（可选，缺失时回退到 len//4 粗略估算）
"""

from src.core.detector_base import ActiveDetector
from src.core.models import CheckResultV2, Issue, IssueLevel
from ..config import WEIGHTS, CATEGORIES

# ─── 可选的 tiktoken 集成 ───────────────────────────────────────
try:
    import tiktoken
    _HAS_TIKTOKEN = True

    def _count_tokens(text: str) -> int:
        """用 tiktoken cl100k_base 精确计算 token 数（GPT-4o/GPT-4 兼容）"""
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
except ImportError:
    _HAS_TIKTOKEN = False

    def _count_tokens(text: str) -> int:
        """回退方案：1 token ≈ 4 字符"""
        return max(1, len(text) // 4)


_KNOWN_PROMPT = "Write a haiku about artificial intelligence in exactly three lines."

# 消息格式开销：API 的 prompt_tokens 包含消息结构 token（role 标记、分隔符等），
# 而非纯文本 token。OpenAI chat 格式约 4 token 开销（<|im_start|>user\n...<|im_end|>\n）。
_MESSAGE_FORMAT_OVERHEAD = 4

_KNOWN_PROMPT_TOKENS = (_count_tokens(_KNOWN_PROMPT) + _MESSAGE_FORMAT_OVERHEAD) if _HAS_TIKTOKEN else None


class BillingIntegrityDetector(ActiveDetector):
    """计费完整性检测器（OpenAI 协议，v2.2）"""

    name = "billing_integrity"
    category = CATEGORIES["billing_integrity"]
    weight = WEIGHTS["billing_integrity"]
    modes = ["standard", "full"]
    timeout = 15
    estimated_tokens = 2000  # v2.5: 设置合理预估，实际消耗约 1500-2000 tokens

    def run(self, client) -> CheckResultV2:
        issues: list[Issue] = []
        score = 100

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

        # ── 1. Tokenizer 精度校验 ────────────────────────────
        reported_input = usage.prompt_tokens
        if _HAS_TIKTOKEN and _KNOWN_PROMPT_TOKENS:
            actual_input = _KNOWN_PROMPT_TOKENS
            input_deviation = (reported_input - actual_input) / max(actual_input, 1) * 100
        else:
            # 回退：用当前 prompt 实时估算（含格式开销）
            estimated_input = _count_tokens(_KNOWN_PROMPT) + _MESSAGE_FORMAT_OVERHEAD
            input_deviation = (reported_input - estimated_input) / max(estimated_input, 1) * 100

        precision_parts = [
            f"reported_input={reported_input}",
            f"estimated_input={_KNOWN_PROMPT_TOKENS or 'n/a'}",
            f"overhead={_MESSAGE_FORMAT_OVERHEAD}",
            f"deviation={input_deviation:+.1f}%",
            f"tokenizer={'tiktoken' if _HAS_TIKTOKEN else 'chars/4'}",
        ]

        if abs(input_deviation) > 30:
            score -= 40
            issues.append(Issue(level=IssueLevel.MAJOR,
                message=f"prompt_tokens 偏差 {input_deviation:+.0f}%！上报 {reported_input}，实际约 {_KNOWN_PROMPT_TOKENS or '?'}",
                detector_name=self.name))
        elif abs(input_deviation) > 10:
            score -= 20
            issues.append(Issue(level=IssueLevel.MINOR,
                message=f"prompt_tokens 偏差 {input_deviation:+.0f}%（上报 {reported_input}）",
                detector_name=self.name))
        else:
            issues.append(Issue(level=IssueLevel.OK,
                message=f"prompt_tokens 精度正常（偏差 {input_deviation:+.1f}%）",
                detector_name=self.name))

        # ── 2. Cache 字段审计 ────────────────────────────────
        cache_create = usage.cache_creation_input_tokens
        cache_read = usage.cache_read_input_tokens
        if cache_create > 0 or cache_read > 0:
            precision_parts.append(f"cache_create={cache_create}")
            precision_parts.append(f"cache_read={cache_read}")
            issues.append(Issue(level=IssueLevel.MAJOR,
                message=f"非缓存请求却返回 cache 字段（creation={cache_create}, read={cache_read}）",
                detector_name=self.name))
            score -= 30
        else:
            precision_parts.append("cache=无")
            issues.append(Issue(level=IssueLevel.OK, message="未检测到异常 cache 计费字段", detector_name=self.name))

        # ── 3. 输出 token 精度校验 ───────────────────────────
        reported_output = usage.completion_tokens
        content = resp.content or ""
        estimated_output = _count_tokens(content)
        if estimated_output > 0:
            output_deviation = (reported_output - estimated_output) / estimated_output * 100
            precision_parts.append(f"reported_output={reported_output}")
            precision_parts.append(f"estimated_output={estimated_output}")
            precision_parts.append(f"output_deviation={output_deviation:+.1f}%")
            if abs(output_deviation) > 50:
                score -= 20
                issues.append(Issue(level=IssueLevel.MAJOR,
                    message=f"completion_tokens 偏差 {output_deviation:+.0f}%", detector_name=self.name))
            elif abs(output_deviation) > 20:
                score -= 15
                issues.append(Issue(level=IssueLevel.MINOR,
                    message=f"completion_tokens 偏差 {output_deviation:+.0f}%", detector_name=self.name))

        # ── 4. 计费倍率 ──────────────────────────────────────
        estimated_total = (_KNOWN_PROMPT_TOKENS or (_count_tokens(_KNOWN_PROMPT) + _MESSAGE_FORMAT_OVERHEAD)) + estimated_output
        reported_total = reported_input + reported_output
        multiplier = reported_total / max(estimated_total, 1)
        precision_parts.append(f"multiplier={multiplier:.2f}x")
        precision_parts.append(f"reported_total={reported_total}")
        precision_parts.append(f"estimated_total={estimated_total}")

        if multiplier > 2.0:
            score -= 20
            issues.append(Issue(level=IssueLevel.CRITICAL,
                message=f"计费倍率 {multiplier:.1f}x！严重虚报",
                detector_name=self.name))
        elif multiplier > 1.5:
            score -= 10
            issues.append(Issue(level=IssueLevel.MAJOR,
                message=f"计费倍率 {multiplier:.1f}x，显著通胀",
                detector_name=self.name))
        elif multiplier > 1.2:
            issues.append(Issue(level=IssueLevel.MINOR,
                message=f"计费倍率 {multiplier:.1f}x，轻微通胀",
                detector_name=self.name))
        else:
            issues.append(Issue(level=IssueLevel.OK,
                message=f"计费倍率 {multiplier:.2f}x，计费透明度正常",
                detector_name=self.name))

        score = max(0, min(100, score))
        return CheckResultV2(
            name=self.name, category=self.category, score=score, weight=self.weight,
            cost_tokens=usage.total_tokens if usage else 0,
            details=" | ".join(precision_parts),
            issues=issues,
        )
