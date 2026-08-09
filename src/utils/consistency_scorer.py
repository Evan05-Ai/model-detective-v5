"""consistency_scorer - 一致性检测多维度评分工具（v2.7）

提供三维度加权评分的共享计算逻辑，供各协议的 consistency 检测器使用：

维度一：答案一致性 (40%)
  - 基于字符串相似度的渐进式评分
  - 完全一致 -> 95, 2种变体 -> 55-78, 3种变体 -> 30-55

维度二：特征稳定性 (30%)
  - 长度变异系数 (CV)
  - 行数变异系数
  - 格式一致性（首字符、标点模式）

维度三：语义相似度 (30%)
  - Jaccard 指数（词汇重叠）
  - 非线性映射，适应创意写作的低重叠特性
"""

import re
import math
from difflib import SequenceMatcher

# 简单停用词表
_STOPWORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "must", "shall", "can", "need", "dare",
    "to", "of", "in", "for", "on", "with", "at", "by", "from", "as",
    "into", "through", "during", "before", "after", "above", "below",
    "up", "down", "out", "off", "over", "under", "again", "further",
    "then", "once", "here", "there", "all", "any", "both", "each",
    "few", "more", "most", "other", "some", "such", "no", "nor", "not",
    "only", "own", "same", "so", "than", "too", "very", "s", "t",
    "just", "don", "now", "i", "me", "my", "we", "our", "you", "your",
    "he", "him", "his", "she", "her", "it", "its", "they", "them",
    "their", "what", "which", "who", "whom", "this", "that", "these",
    "those", "and", "but", "or", "if", "while", "about", "against",
    "between", "itself", "also", "write", "haiku", "ai", "3", "5", "7",
    "lines", "line", "syllables", "about",
})

# 各维度权重
W_ANSWER_CONSISTENCY = 0.40
W_FEATURE_STABILITY = 0.30
W_SEMANTIC_SIMILARITY = 0.30

# 创意写作问题（避免数学确定性陷阱）
HAIKU_QUESTION = "Write a haiku about AI (3 lines, 5-7-5 syllables)."


def calc_answer_consistency(responses: list[str]) -> float:
    """答案一致性评分 (40%)

    v2.7 渐进式评分，消除二元化跳跃：
    - 完全一致 -> 95
    - 2种变体 -> 基于字符串相似度在 55-78 之间渐进
    - 3种变体 -> 基于两两平均相似度在 30-55 之间渐进
    """
    unique = set(responses)
    n = len(responses)

    if len(unique) == 1:
        return 95.0

    if len(unique) == 2:
        unique_list = list(unique)
        sim = _string_similarity(unique_list[0], unique_list[1])
        return 55.0 + sim * 23.0

    # 3种变体
    sims = []
    for i in range(n):
        for j in range(i + 1, n):
            sims.append(_string_similarity(responses[i], responses[j]))
    avg_sim = sum(sims) / len(sims) if sims else 0.0
    return 30.0 + avg_sim * 25.0


def calc_feature_stability(responses: list[str]) -> float:
    """特征稳定性评分 (30%)

    检测响应结构化特征一致性：
    - 长度一致性（字符数变异系数）
    - 行数一致性（行数变异系数）
    - 格式一致性（首字符、标点模式）
    """
    n = len(responses)

    # --- 长度特征 ---
    lengths = [len(r) for r in responses]
    length_mean = sum(lengths) / n
    if n > 1 and length_mean > 0:
        length_var = sum((l - length_mean) ** 2 for l in lengths) / n
        length_cv = math.sqrt(length_var) / length_mean * 100
    else:
        length_cv = 0.0
    length_score = max(20.0, 100.0 - length_cv)

    # --- 行数特征 ---
    line_counts = [r.count("\n") + 1 for r in responses if r.strip()]
    if len(line_counts) == n and n > 1:
        line_mean = sum(line_counts) / n
        if line_mean > 0:
            line_var = sum((c - line_mean) ** 2 for c in line_counts) / n
            line_cv = math.sqrt(line_var) / line_mean * 100
        else:
            line_cv = 0.0
        line_score = max(20.0, 100.0 - line_cv)
    else:
        line_score = 50.0

    # --- 格式特征 ---
    first_chars = [r[0] if r else "" for r in responses]
    format_consistent = len(set(first_chars)) == 1

    punct_patterns = [set(re.findall(r"[.!?,;:]", r)) for r in responses]
    punct_consistent = len(set(frozenset(p) for p in punct_patterns)) == 1

    format_score = 50.0
    if format_consistent:
        format_score += 25.0
    if punct_consistent:
        format_score += 25.0

    return length_score * 0.4 + line_score * 0.4 + min(100.0, format_score) * 0.2


def calc_semantic_similarity(responses: list[str]) -> float:
    """语义相似度评分 (30%)

    基于词汇重叠（Jaccard 指数），非线性映射
    """
    n = len(responses)

    token_sets = []
    for r in responses:
        words = set(re.findall(r"\b\w+\b", r.lower()))
        words -= _STOPWORDS
        token_sets.append(words)

    jaccards = []
    for i in range(n):
        for j in range(i + 1, n):
            union = token_sets[i] | token_sets[j]
            if union:
                jaccards.append(len(token_sets[i] & token_sets[j]) / len(union))
            else:
                jaccards.append(0.0)

    avg_jaccard = sum(jaccards) / len(jaccards) if jaccards else 0.0

    if avg_jaccard <= 0:
        return 20.0
    return min(95.0, 20.0 + avg_jaccard * 150.0)


def calc_confidence(
    responses: list[str], score: float
) -> tuple[float, str]:
    """计算置信度和说明"""
    n = len(responses)
    unique = set(responses)

    if score >= 85:
        return 0.92, f"{n}次请求响应高度一致（{len(unique)}种变体）"
    elif score >= 70:
        return 0.85, f"{n}次请求响应基本一致（{len(unique)}种变体）"
    elif score >= 50:
        return 0.78, f"{n}次请求返回{len(unique)}种变体，一致性中等"
    elif score >= 30:
        return 0.80, f"{n}次请求返回{len(unique)}种变体，一致性较差"
    else:
        return 0.85, f"{n}次请求返回{len(unique)}种完全不同的响应，一致性极差"


def generate_issues(
    responses: list[str],
    consistency: float,
    feature: float,
    semantic: float,
    detector_name: str,
) -> list:
    """根据评分生成 Issues"""
    from src.core.models import Issue, IssueLevel

    issues = []
    unique = set(responses)

    if len(unique) >= 3:
        issues.append(
            Issue(
                level=IssueLevel.MAJOR,
                message=(
                    f"3次请求返回3种完全不同的响应，"
                    f"temperature=0时不应如此不稳定"
                ),
                detector_name=detector_name,
            )
        )
    elif len(unique) == 2:
        issues.append(
            Issue(
                level=IssueLevel.MINOR,
                message=(
                    f"3次请求返回2种不同响应，"
                    f"可能存在轻微不一致（格式差异或采样波动）"
                ),
                detector_name=detector_name,
            )
        )

    if feature < 50:
        issues.append(
            Issue(
                level=IssueLevel.MINOR,
                message=f"响应特征（长度/行数）波动较大，特征稳定性={feature:.0f}",
                detector_name=detector_name,
            )
        )

    if semantic < 40:
        issues.append(
            Issue(
                level=IssueLevel.MINOR,
                message=f"响应语义相似度较低，词汇重叠度={semantic:.0f}",
                detector_name=detector_name,
            )
        )

    return issues


def score_responses(responses: list[str]) -> tuple[float, float, float, float]:
    """计算三维度评分并返回加权总分

    Returns:
        (final_score, consistency_score, feature_score, semantic_score)
    """
    c = calc_answer_consistency(responses)
    f = calc_feature_stability(responses)
    s = calc_semantic_similarity(responses)
    final = round(
        c * W_ANSWER_CONSISTENCY
        + f * W_FEATURE_STABILITY
        + s * W_SEMANTIC_SIMILARITY
    )
    return final, c, f, s


def _string_similarity(a: str, b: str) -> float:
    """字符串相似度（基于 SequenceMatcher）"""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()
