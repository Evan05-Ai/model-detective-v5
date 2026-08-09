"""identity_analyzer - 身份认知分析工具（v2.7）

提供语义理解级别的身份分析逻辑，供各协议的 identity 检测器使用：

1. 否定语境检测
   - "I am Claude"           → positive（肯定匹配）
   - "I am not Claude"       → negated（否定匹配，不误判）
   - "Unlike Claude, I am GPT" → comparative negation（比较否定）

2. 智能拒绝检测
   - 纯拒绝: "I cannot answer that"                     → is_refusal=True
   - 部分拒绝+回答: "I can't say for sure, but I'm Claude" → is_refusal=False（视为有效回答）
   - 无拒绝: "I am Claude 3.5 Sonnet"                     → is_refusal=False

3. 跨策略一致性验证
   - 所有策略返回相同身份 → 高一致性
   - 策略间返回不同身份 → 低一致性，标记 MAJOR issue

4. 渐进式评分（消除二元化跳跃）
   - 完全匹配（含版本）→ 95
   - 身份匹配（版本不符）→ 82-90
   - 模糊/无法明确识别 → 45-60
   - 明确不匹配       → 15-25
   - 全部拒绝         → 35（不直接判失败）
   - 策略间不一致     → 20-30
"""

import re
from dataclasses import dataclass, field
from typing import Optional


# ============================================================
# 身份关键词定义
# ============================================================

IDENTITY_PATTERNS: dict[str, dict] = {
    "claude": {
        "keywords": ["claude", "anthropic"],
        "versions": ["sonnet", "opus", "haiku", "3.5", "3.7", "4"],
    },
    "gpt": {
        "keywords": ["gpt", "openai", "chatgpt"],
        "versions": ["4o", "4", "3.5", "turbo", "davinci", "o1", "o3"],
    },
    "gemini": {
        "keywords": ["gemini", "bard", "google ai"],
        "versions": ["pro", "ultra", "flash", "1.5", "2.0", "2.5"],
    },
    "kiro": {
        "keywords": ["kiro", "amazon q", "aws", "bedrock",
                      "code whisperer", "q developer"],
        "versions": [],
    },
    "opensource": {
        "keywords": ["qwen", "deepseek", "llama", "mistral",
                      "yi-", "yi-01", "zhipu", "chatglm"],
        "versions": [],
    },
}

# 按优先级排序（检查顺序）
_IDENTITY_ORDER = ["claude", "gpt", "gemini", "kiro", "opensource"]


# ============================================================
# 拒绝检测模式
# ============================================================

# 纯拒绝模式（整个回答都是拒绝，没有有效身份信息）
PURE_REFUSAL_PATTERNS = [
    # "I cannot/can't answer/confirm/provide..."
    r"(?:i\s+)?(?:cannot|can'?t|could\s+not|couldn'?t|will\s+not|won'?t)\s+"
    r"(?:answer|confirm|provide|disclose|share|reveal|say|state|tell)",
    # "I am not able/allowed/permitted to..."
    r"(?:i\s+)?(?:am\s+not|'m\s+not)\s+(?:able|allowed|permitted|authorized)\s+to\s+"
    r"(?:answer|confirm|provide|disclose|share|reveal)",
    # "I don't have access/permission to..."
    r"(?:i\s+)?(?:don'?t|do\s+not)\s+have\s+(?:access|permission)\s+to",
    # "I'm not at liberty to..."
    r"(?:i\s+)?(?:am\s+not|'m\s+not)\s+at\s+liberty\s+to",
    # Chinese
    r"无法(?:确认|回答|提供|透露|告知|说明)",
    r"不能(?:回答|透露|告知|说明)",
    r"无法提供",
]

# 部分拒绝模式（拒绝之后仍然给出了身份信息）
PARTIAL_REFUSAL_PATTERNS = [
    # "I can't say for sure, but I am/think..."
    r"(?:i\s+)?(?:can'?t|cannot|could\s+not).{0,80}"
    r"(?:but|however|though|while).{0,120}"
    r"(?:i\s+)?(?:am|'m|think|believe|assume|guess|suppose)",
    # "I'm not sure, but I think I'm..."
    r"(?:i\s+)?(?:am\s+not|'m\s+not)\s+(?:exactly\s+)?sure.{0,80}"
    r"(?:but|however|though).{0,120}"
    r"(?:i\s+)?(?:am|'m|think|believe|assume|guess|suppose)",
    # "I can't confirm exactly, but I believe..."
    r"(?:i\s+)?(?:can'?t|cannot).{0,60}(?:confirm|say|state).{0,60}"
    r"(?:but|however|though).{0,100}"
    r"(?:i\s+)?(?:am|'m|think|believe|assume|guess|suppose)",
]

# 否定前缀（检查关键词前是否有否定）
_NEGATION_WORDS = [
    r"not\s+", r"n'?t\s+", r"never\s+", r"no\s+",
]

# 比较否定模式
_COMPARATIVE_NEGATION = [
    r"unlike\s+",
    r"as\s+opposed\s+to\s+",
    r"different\s+from\s+",
    r"instead\s+of\s+",
    r"rather\s+than\s+",
    r"not\s+to\s+be\s+confused\s+with\s+",
]


# ============================================================
# 数据结构
# ============================================================

@dataclass
class IdentityExtraction:
    """从单个响应中提取的身份信息"""
    identity: str = "unknown"      # claude, gpt, gemini, kiro, opensource, unknown
    match_type: str = "none"       # positive, negated, none
    keyword: str = ""              # 匹配到的关键词
    version: str = ""              # 检测到的版本
    is_refusal: bool = False       # 是否纯拒绝
    is_partial_refusal: bool = False  # 是否部分拒绝
    refusal_degree: float = 0.0    # 0-1 拒绝程度
    raw_content: str = ""          # 原始内容


@dataclass
class AnalysisResult:
    """跨策略分析结果"""
    score: float = 50.0
    confidence: float = 0.5
    confidence_reason: str = ""
    details: str = ""
    issues: list = field(default_factory=list)
    extractions: list[IdentityExtraction] = field(default_factory=list)


# ============================================================
# 核心函数
# ============================================================

def extract_identity(content: str) -> IdentityExtraction:
    """从响应中提取身份信息，支持否定检测

    核心逻辑：
    1. 遍历所有身份模式，查找关键词
    2. 对每个匹配到的关键词，检查是否被否定
    3. 返回第一个 positive 匹配（如果有的话）
    4. 如果所有匹配都是 negated，返回 negated 结果
    """
    if not content or len(content.strip()) < 5:
        return IdentityExtraction(raw_content=content or "")

    content_lower = content.lower()

    # 先检查是否是拒绝
    is_pure_refusal, is_partial, refusal_deg = _detect_refusal(content)

    if is_pure_refusal:
        return IdentityExtraction(
            is_refusal=True,
            refusal_degree=1.0,
            raw_content=content,
        )

    # 遍历身份模式
    first_negated = None
    for identity_name in _IDENTITY_ORDER:
        patterns = IDENTITY_PATTERNS[identity_name]
        for keyword in patterns["keywords"]:
            if keyword in content_lower:
                # 检查否定
                is_negated = _check_negation(content_lower, keyword)

                if is_negated:
                    if first_negated is None:
                        first_negated = IdentityExtraction(
                            identity=identity_name,
                            match_type="negated",
                            keyword=keyword,
                            is_partial_refusal=is_partial,
                            refusal_degree=refusal_deg,
                            raw_content=content,
                        )
                    continue

                # positive match
                version = _detect_version(content_lower, patterns.get("versions", []))
                return IdentityExtraction(
                    identity=identity_name,
                    match_type="positive",
                    keyword=keyword,
                    version=version,
                    is_partial_refusal=is_partial,
                    refusal_degree=refusal_deg,
                    raw_content=content,
                )

    # 如果有 negated 匹配但没有 positive 匹配
    if first_negated:
        return first_negated

    # 未匹配到任何身份关键词
    return IdentityExtraction(
        match_type="none",
        is_partial_refusal=is_partial,
        refusal_degree=refusal_deg,
        raw_content=content,
    )


def _detect_refusal(content: str) -> tuple[bool, bool, float]:
    """检测拒绝回答

    Returns:
        (is_pure_refusal, is_partial_refusal, refusal_degree)
        - Pure refusal: (True, False, 1.0)
        - Partial refusal: (False, True, 0.3-0.7)
        - No refusal: (False, False, 0.0)
    """
    content_lower = content.lower().strip()

    # 检查纯拒绝
    for pattern in PURE_REFUSAL_PATTERNS:
        if re.search(pattern, content_lower):
            # 检查是否同时包含身份关键词（如果是，则为部分拒绝）
            has_identity = any(
                kw in content_lower
                for id_patterns in IDENTITY_PATTERNS.values()
                for kw in id_patterns["keywords"]
            )
            if has_identity:
                # 部分拒绝：拒绝了但仍然透露了身份
                return (False, True, 0.5)
            else:
                # 纯拒绝
                return (True, False, 1.0)

    # 检查部分拒绝
    for pattern in PARTIAL_REFUSAL_PATTERNS:
        if re.search(pattern, content_lower):
            return (False, True, 0.4)

    return (False, False, 0.0)


def _check_negation(content_lower: str, keyword: str) -> bool:
    """检查关键词是否被否定

    检查模式：
    1. "not [a/an/the] keyword" → 直接否定
    2. "keyword ... not [real/actual/true]" → 后置否定
    3. "unlike keyword" → 比较否定
    4. Chinese: "不是...keyword", "并非...keyword"
    """
    # 1. 直接否定: "not [a/an/the] keyword"
    # 允许中间最多4个词
    direct_neg = rf"\b(?:not|n't|never|no)\s+(?:\w+\s+){{0,4}}{re.escape(keyword)}"
    if re.search(direct_neg, content_lower):
        return True

    # 2. 后置否定: "keyword ... not [real/actual/true/correct]"
    post_neg = rf"{re.escape(keyword)}.{{0,40}}\bnot\s+(?:real|actual|true|correct|right|genuine)"
    if re.search(post_neg, content_lower):
        return True

    # 3. 比较否定: "unlike/as opposed to keyword"
    for comp_pattern in _COMPARATIVE_NEGATION:
        comp_regex = comp_pattern + rf"(?:a\s+|an\s+|the\s+)?{re.escape(keyword)}"
        if re.search(comp_regex, content_lower):
            return True

    # 4. Chinese negation (proximity=5 to avoid cross-identity false positives)
    cn_neg = rf"不是.{{0,5}}{re.escape(keyword)}"
    if re.search(cn_neg, content_lower):
        return True
    cn_neg2 = rf"并非.{{0,5}}{re.escape(keyword)}"
    if re.search(cn_neg2, content_lower):
        return True
    cn_neg3 = rf"不同于.{{0,5}}{re.escape(keyword)}"
    if re.search(cn_neg3, content_lower):
        return True

    # 5. "no, [I'm] not [a] keyword"
    no_not = rf"\bno[,.]?\s+(?:i\s+)?(?:am\s+|'m\s+)?not\s+(?:a\s+|an\s+|the\s+)?{re.escape(keyword)}"
    if re.search(no_not, content_lower):
        return True

    return False


def _detect_version(content_lower: str, versions: list[str]) -> str:
    """检测版本信息"""
    if not versions:
        return ""
    for v in versions:
        if v in content_lower:
            return v
    return ""


def _identity_matches_claimed(identity: str, claimed_model: str) -> bool:
    """检查提取的身份是否与声称的模型匹配"""
    claimed_lower = claimed_model.lower()
    if identity == "claude":
        return any(kw in claimed_lower for kw in ["claude", "anthropic"])
    elif identity == "gpt":
        return any(kw in claimed_lower for kw in ["gpt", "openai"])
    elif identity == "gemini":
        return any(kw in claimed_lower for kw in ["gemini", "google"])
    elif identity == "kiro":
        return any(kw in claimed_lower for kw in ["kiro", "aws", "bedrock"])
    elif identity == "opensource":
        return any(kw in claimed_lower for kw in ["qwen", "deepseek", "llama", "mistral", "yi-"])
    return False


def _version_matches(extractions: list[IdentityExtraction], claimed_model: str) -> bool:
    """检查版本是否匹配"""
    claimed_lower = claimed_model.lower()
    for ext in extractions:
        if ext.match_type == "positive" and ext.version:
            if ext.version in claimed_lower:
                return True
    return False


# ============================================================
# 跨策略分析 & 评分
# ============================================================

def analyze_responses(
    responses: list[dict],
    claimed_model: str,
    detector_name: str = "identity",
) -> AnalysisResult:
    """分析所有策略的响应，给出综合评分

    Args:
        responses: [{"strategy": int, "response": str, ...}]
        claimed_model: 声称的模型名
        detector_name: 检测器名称（用于 Issue）

    Returns:
        AnalysisResult 包含 score, confidence, issues, details
    """
    from src.core.models import Issue, IssueLevel

    result = AnalysisResult()
    total = len(responses)

    if total == 0:
        result.score = 0
        result.confidence = 0.0
        result.confidence_reason = "无响应数据"
        result.details = "无响应数据"
        return result

    # 提取所有响应的身份信息
    extractions: list[IdentityExtraction] = []
    for r in responses:
        ext = extract_identity(r.get("response", ""))
        extractions.append(ext)
    result.extractions = extractions

    # 统计
    refusals = [e for e in extractions if e.is_refusal]
    partials = [e for e in extractions if e.is_partial_refusal]
    positives = [e for e in extractions if e.match_type == "positive"]
    negateds = [e for e in extractions if e.match_type == "negated"]
    unknowns = [e for e in extractions if e.match_type == "none" and not e.is_refusal]

    refusal_count = len(refusals)
    positive_count = len(positives)
    total_valid = total - refusal_count

    # ---- 场景1: 全部拒绝 ----
    if refusal_count == total:
        result.score = 35
        result.confidence = 0.2
        result.confidence_reason = (
            f"所有 {total} 种策略均被拒绝，无法获得有效身份信息"
        )
        result.issues.append(Issue(
            level=IssueLevel.MINOR,
            message=(
                f"模型拒绝确认身份（{refusal_count}/{total} 次拒绝）。"
                f"可能原因：系统提示约束、安全策略、或中转站添加了身份隐藏层。"
                f"建议结合其他检测项综合判断。"
            ),
            detector_name=detector_name,
        ))
        result.details = f"全部拒绝（{total}/{total}）"
        return result

    # ---- 场景2: 无 positive 匹配（全是 negated/unknown） ----
    if positive_count == 0:
        if negateds:
            # 有否定匹配但无肯定匹配 → 模型否认了某个身份但未明确自己是什么
            result.score = 30
            result.confidence = 0.6
            negated_id = negateds[0].identity
            result.confidence_reason = (
                f"模型否认了 {negated_id} 身份，但未明确自己的真实身份"
            )
            result.issues.append(Issue(
                level=IssueLevel.MAJOR,
                message=(
                    f"模型否认身份 '{negated_id}' 但未自报身份，"
                    f"可能是中转站伪装的模型"
                ),
                detector_name=detector_name,
            ))
        else:
            # 全是 unknown（回答模糊）
            result.score = 45
            result.confidence = 0.4
            result.confidence_reason = (
                f"模型回答模糊，无法明确识别身份"
                f"（{total - refusal_count}/{total} 次有效回答但无身份信息）"
            )
            result.issues.append(Issue(
                level=IssueLevel.MINOR,
                message=(
                    f"模型回答模糊，无法明确识别身份"
                    f"（{len(unknowns)}/{total} 次模糊回答）"
                ),
                detector_name=detector_name,
            ))
        result.details = f"无肯定匹配 | 拒绝={refusal_count} 否定={len(negateds)} 模糊={len(unknowns)}"
        return result

    # ---- 场景3: 有 positive 匹配 ----

    # 跨策略一致性检查
    positive_identities = set(e.identity for e in positives)
    is_consistent = len(positive_identities) == 1

    if not is_consistent:
        # 策略间身份不一致
        result.score = 25
        result.confidence = 0.85
        result.confidence_reason = (
            f"策略间身份不一致：{list(positive_identities)}"
        )
        result.issues.append(Issue(
            level=IssueLevel.MAJOR,
            message=(
                f"不同询问策略得到不同的身份信息: "
                f"{[e.identity for e in positives]}"
            ),
            detector_name=detector_name,
        ))
        result.details = f"不一致 | 身份={list(positive_identities)}"
        return result

    # 所有 positive 匹配一致
    identity = positives[0].identity
    matches_claimed = _identity_matches_claimed(identity, claimed_model)
    version_matched = _version_matches(positives, claimed_model)

    # ---- Kiro/AWS 代理链路特殊处理（优先检查）----
    # Kiro 身份与 Claude 模型名不直接匹配（_identity_matches_claimed 返回 False），
    # 因此必须在正常匹配逻辑之前处理，否则 Claude+Kiro 场景会错误地进入
    # "身份不匹配" 分支，得到 20 分 + CRITICAL 评级。
    kiro_handled = False
    if identity == "kiro":
        kiro_handled = True
        if "claude" in claimed_model.lower():
            # 声称的是 Claude 模型，但自报为 Kiro → Kiro 代理的真实 Claude
            result.score = 75  # 给予较高分数，因为可能是真实 Claude
            result.confidence = 0.75
            result.confidence_reason = (
                f"模型自报为 Kiro 环境（'{positives[0].keyword}'），"
                f"但声称模型为 {claimed_model}。"
                f"这是典型的 Kiro 代理 Claude 场景，模型本身可能是真实的。"
            )
            result.issues.append(Issue(
                level=IssueLevel.OK,
                message=(
                    f"模型在 Kiro 环境中运行（检测到 '{positives[0].keyword}'）。"
                    f"Kiro 是 AWS 的 AI 开发环境，模型自报为 Kiro 是正常行为。"
                    f"结合声称的模型名 '{claimed_model}'，这很可能是真实的 Claude 模型。"
                ),
                detector_name=detector_name,
            ))
        else:
            # 声称的不是 Claude，但自报为 Kiro
            result.score = 55
            result.confidence = 0.7
            result.confidence_reason = (
                "模型自报为 Kiro/AWS 链路身份，"
                "与声称的模型可能不匹配"
            )
            result.issues.append(Issue(
                level=IssueLevel.MEDIUM,
                message=(
                    "模型自报为 Kiro/AWS 身份。"
                    "请求经过 Kiro 链路转发，建议结合其他检测项验证模型真实性。"
                ),
                detector_name=detector_name,
            ))

    if not kiro_handled:
        if matches_claimed:
            # 身份匹配
            if version_matched:
                result.score = 95
                result.confidence = 0.95
                result.confidence_reason = (
                    f"模型明确确认 {identity}（含版本）身份，"
                    f"与声称的 {claimed_model} 匹配"
                )
                result.issues.append(Issue(
                    level=IssueLevel.OK,
                    message=(
                        f"模型确认身份（{positive_count}/{total} 策略一致），"
                        f"版本匹配"
                    ),
                    detector_name=detector_name,
                ))
            else:
                # 身份匹配但版本不符不明确
                result.score = 85
                result.confidence = 0.90
                result.confidence_reason = (
                    f"模型确认 {identity} 身份，与声称匹配，"
                    f"但版本细节不完全匹配"
                )
                result.issues.append(Issue(
                    level=IssueLevel.OK,
                    message=(
                        f"模型确认 {identity} 身份（{positive_count}/{total} 策略一致），"
                        f"版本细节不明确"
                    ),
                    detector_name=detector_name,
                ))
        else:
            # 身份不匹配
            result.score = 20
            result.confidence = 0.85
            result.confidence_reason = (
                f"模型明确自报为 {identity}，与声称的 {claimed_model} 不符"
            )
            result.issues.append(Issue(
                level=IssueLevel.CRITICAL,
                message=(
                    f"模型自报为 {identity}，"
                    f"与声称的 {claimed_model} 不符。"
                    f"这强烈暗示中转站使用了不同的模型。"
                ),
                detector_name=detector_name,
            ))

    # 部分拒绝降分
    if partials:
        penalty = min(10, len(partials) * 3)
        result.score = max(10, result.score - penalty)
        result.confidence = max(0.3, result.confidence - 0.05 * len(partials))
        result.confidence_reason += f"，{len(partials)} 种策略部分拒绝"
        result.issues.append(Issue(
            level=IssueLevel.MINOR,
            message=(
                f"{len(partials)} 种策略出现部分拒绝"
                f"（拒绝后仍给出了身份信息）"
            ),
            detector_name=detector_name,
        ))

    # 纯拒绝降分
    if refusal_count > 0:
        penalty = min(15, refusal_count * 5)
        result.score = max(10, result.score - penalty)
        result.confidence = max(0.3, result.confidence - 0.08 * refusal_count)
        result.confidence_reason += f"，{refusal_count} 种策略被拒绝"

    # 确保分数和置信度在合理范围
    result.score = max(0, min(100, result.score))
    result.confidence = max(0.0, min(1.0, result.confidence))

    # 生成 details
    sample_response = ""
    for e in extractions:
        if e.match_type == "positive":
            sample_response = e.raw_content[:120]
            break
    if not sample_response and extractions:
        sample_response = extractions[-1].raw_content[:120]

    result.details = (
        f"策略={total} 肯定={positive_count} 拒绝={refusal_count} "
        f"否定={len(negateds)} 模糊={len(unknowns)} | "
        f"身份={identity} 匹配={matches_claimed} 版本={version_matched} | "
        f"回复: {sample_response}"
    )

    return result
