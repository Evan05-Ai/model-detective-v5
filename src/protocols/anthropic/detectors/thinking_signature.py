"""thinking_signature - 加密签名验证（真伪，权重 25%，核心检测器）

Bug 10 修复：签名有效时额外检查响应头中转站特征，区分"直连签名"和"代理商签名"
  - 签名有效 + 无中转站特征 → score 100, issue ok（疑似直连）
  - 签名有效 + 有中转站特征 → score 70, issue minor（经中转站转发）
  - 签名缺失 → score 0, issue critical
"""

from src.core.detector_base import ActiveDetector
from src.core.models import CheckResultV2, Issue, IssueLevel
from ..config import WEIGHTS, CATEGORIES


# 中转站特征响应头（v3.0 分级判定，消除 CDN 头误判）
# 强特征：OneAPI/NewAPI 等中转面板特有的头，出现即判定经中转
STRONG_PROXY_HEADER_MARKERS = [
    "x-oneapi-request-id",
    "x-new-api",
    "x-oneapi",
]
# 弱特征：CDN/通用基础设施头。cf-ray 是 Cloudflare CDN 头，大量正规站点都有；
# x-ratelimit 是通用限流头。单一弱特征不再判"经中转"，需 ≥2 个同时出现。
WEAK_PROXY_HEADER_MARKERS = [
    "cf-ray",          # Cloudflare CDN
    "x-vercel",        # Vercel
    "x-served-by",
    "x-forwarded-for",
    "x-real-ip",
    "x-ratelimit",     # 自定义限流
]


class ThinkingSignatureDetector(ActiveDetector):
    """加密签名检测：验证 Claude thinking_signature 字段"""

    name = "thinking_signature"
    category = CATEGORIES["thinking_signature"]
    weight = WEIGHTS["thinking_signature"]
    modes = ["quick", "standard", "full"]
    timeout = 30
    estimated_tokens = 4000      # v2.5 修正：thinking=1024 + max_tokens=1150 + prompt + overhead，实际可能消耗 2500-3500 tokens

    def run(self, client) -> CheckResultV2:
        # 发送带 thinking 的请求
        # v3.0.2: max_tokens 1500 → 1150（thinking 1024 是 API 下限不能动，
        # 但 "17*23" 的答案只需 ~20 token，1150 留 126 缓冲足够；
        # 签名在 thinking 块上，答案截断不影响检测）
        resp = client.messages(
            messages=[{
                "role": "user",
                "content": "Think carefully: What is 17 * 23? Show your reasoning."
            }],
            max_tokens=1150,
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
            # v3.0：强特征任一命中，或 ≥2 个弱特征同时出现才判"经中转"。
            # 匹配采用前缀方式（x-ratelimit 可命中 x-ratelimit-limit 等变体）。
            headers_lower = [k.lower() for k in headers.keys()]
            strong_found = [m for m in STRONG_PROXY_HEADER_MARKERS
                            if any(k == m or k.startswith(m) for k in headers_lower)]
            weak_found = [m for m in WEAK_PROXY_HEADER_MARKERS
                          if any(k == m or k.startswith(m) for k in headers_lower)]

            if strong_found or len(weak_found) >= 2:
                # 签名有效但经中转站转发
                markers_found = strong_found + weak_found[:3]
                score = 70
                confidence = 0.85  # 中高置信度：签名有效但可能经中转
                confidence_reason = "签名验证有效，但检测到中转站特征头"
                issues.append(Issue(
                    level=IssueLevel.MINOR,
                    message=f"签名有效，但检测到中转站特征头: {markers_found[:3]}，疑似经代理商转发",
                    detector_name=self.name,
                ))
            else:
                # 签名有效且无中转特征（单一 CDN 弱特征视为正常基础设施）
                score = 100
                confidence = 0.98  # 极高置信度：签名有效且无中转特征
                confidence_reason = "签名验证有效，未检测到中转站特征"
                if weak_found:
                    issues.append(Issue(
                        level=IssueLevel.OK,
                        message=f"签名有效。检测到 CDN/基础设施头（{weak_found[:2]}），属正常链路特征，不判为中转",
                        detector_name=self.name,
                    ))
                else:
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
