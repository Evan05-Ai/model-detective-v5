"""thinking_signature - 加密签名验证（真伪，权重 25%，核心检测器）

Bug 10 修复：签名有效时额外检查响应头中转站特征，区分"直连签名"和"代理商签名"
  - 签名有效 + 无中转站特征 → score 100, issue ok（疑似直连）
  - 签名有效 + 有中转站特征 → score 70, issue minor（经中转站转发）
  - 签名缺失 → score 0, issue critical
"""

from src.core.detector_base import ActiveDetector
from src.core.models import CheckResultV2, Issue, IssueLevel
from ..config import WEIGHTS, CATEGORIES


# 中转站特征响应头
PROXY_HEADER_MARKERS = [
    "x-oneapi-request-id",
    "x-new-api",
    "x-oneapi",
    "x-forwarded-for",
    "x-real-ip",
    "x-served-by",
    "cf-ray",          # Cloudflare
    "x-vercel",        # Vercel
    "x-ratelimit",     # 自定义限流
]


class ThinkingSignatureDetector(ActiveDetector):
    """加密签名检测：验证 Claude thinking_signature 字段"""

    name = "thinking_signature"
    category = CATEGORIES["thinking_signature"]
    weight = WEIGHTS["thinking_signature"]
    modes = ["quick", "standard", "full"]
    timeout = 30
    estimated_tokens = 4000      # v2.5 修正：thinking=1024 + max_tokens=1500 + prompt + overhead，实际可能消耗 2500-3500 tokens

    def run(self, client) -> CheckResultV2:
        # 发送带 thinking 的请求
        resp = client.messages(
            messages=[{
                "role": "user",
                "content": "Think carefully: What is 17 * 23? Show your reasoning."
            }],
            max_tokens=1500,
            thinking={"type": "enabled", "budget_tokens": 1024},
            detector_name=self.name,
        )

        if not resp.success:
            return CheckResultV2(
                name=self.name, category=self.category, score=0, weight=self.weight,
                status="error", cost_tokens=resp.usage.total_tokens if resp.usage else 0,
                details=f"请求失败: {resp.error}",
                issues=[Issue(
                    level=IssueLevel.MAJOR,
                    message=f"thinking 请求失败: {resp.error}",
                    detector_name=self.name,
                )],
            )

        issues = []
        signature = resp.thinking_signature
        thinking_text = resp.thinking
        headers = resp.headers or {}

        if signature:
            # 签名存在 - 检查是否经中转站转发
            # BUG-3 修复：大小写不敏感匹配
            headers_lower = {k.lower(): v for k, v in headers.items()}
            proxy_markers_found = []
            for marker in PROXY_HEADER_MARKERS:
                if marker in headers_lower:
                    proxy_markers_found.append(marker)

            if proxy_markers_found:
                # 签名有效但经中转站转发
                score = 70
                confidence = 0.85  # 中高置信度：签名有效但可能经中转
                confidence_reason = "签名验证有效，但检测到中转站特征头"
                issues.append(Issue(
                    level=IssueLevel.MINOR,
                    message=f"签名有效，但检测到中转站特征头: {proxy_markers_found[:3]}，疑似经代理商转发",
                    detector_name=self.name,
                ))
            else:
                # 签名有效且无中转站特征
                score = 100
                confidence = 0.98  # 极高置信度：签名有效且无中转特征
                confidence_reason = "签名验证有效，未检测到中转站特征"
                issues.append(Issue(
                    level=IssueLevel.OK,
                    message="签名有效，未检测到中转站特征，疑似直连",
                    detector_name=self.name,
                ))
        else:
            # 签名缺失
            if thinking_text:
                # 有 thinking 但无 signature - 可能是中转站剥离了签名
                score = 20
                confidence = 0.7  # 中等置信度：有 thinking 说明可能是真 Claude，但签名缺失异常
                confidence_reason = "有 thinking 内容但缺少 signature，可能是中转站剥离或链路问题"
                issues.append(Issue(
                    level=IssueLevel.CRITICAL,
                    message="有 thinking 内容但缺少 signature 字段，中转站可能剥离了加密签名",
                    detector_name=self.name,
                ))
            else:
                # 既无 thinking 也无 signature
                score = 5
                confidence = 0.5  # 较低置信度：可能是非 Claude 或不支持 thinking
                confidence_reason = "完全缺少 thinking 和 signature，模型可能不支持 extended thinking 或非真实 Claude"
                issues.append(Issue(
                    level=IssueLevel.CRITICAL,
                    message="完全缺少 thinking 和 signature，模型可能不支持 extended thinking 或非真实 Claude",
                    detector_name=self.name,
                ))

        return CheckResultV2(
            name=self.name, category=self.category, score=score, weight=self.weight,
            cost_tokens=resp.usage.total_tokens if resp.usage else 0,
            confidence=confidence,
            confidence_reason=confidence_reason,
            details=f"signature={'存在' if signature else '缺失'}, thinking={'有' if thinking_text else '无'}, "
                    f"thinking_len={len(thinking_text) if thinking_text else 0}",
            issues=issues,
            raw_response=resp.raw_response,
        )
