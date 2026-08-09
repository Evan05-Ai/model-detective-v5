"""
检测引擎 - 6 种检测方法，按成本从低到高排列

每种检测返回 CheckResult:
  - score: -1 (证据否定) ~ +1 (证据支持)
  - confidence: 0 ~ 1
  - cost_tokens: 消耗的 token 数
  - details: 说明文字
"""

from dataclasses import dataclass
from typing import Optional
from .api_client import APIClient
from .signatures import (
    REAL_OPENAI_MODELS, REAL_ANTHROPIC_MODELS, REAL_GOOGLE_MODELS,
    FAKE_MODEL_PATTERNS, KNOWN_OPEN_SOURCE_MODELS,
    PROVIDER_HEADER_PATTERNS
)


@dataclass
class CheckResult:
    """单项检测结果"""
    name: str
    score: float          # -1 ~ +1
    confidence: float     # 0 ~ 1
    cost_tokens: int      # 消耗的 token 数
    details: str          # 说明
    passed: Optional[bool] = None  # None=不确定, True=通过, False=未通过

    @property
    def cost_label(self) -> str:
        if self.cost_tokens == 0:
            return "FREE"
        elif self.cost_tokens < 50:
            return f"~{self.cost_tokens} tok"
        else:
            return f"{self.cost_tokens} tok"


def check_models_list(client: APIClient) -> CheckResult:
    """检测1: 查询 /v1/models 端点（免费）"""
    success, models, error = client.list_models()

    if not success:
        return CheckResult(
            name="模型列表查询",
            score=0, confidence=0.1, cost_tokens=0,
            details=f"无法查询: {error}",
            passed=None
        )

    # 检查声称的模型是否在列表中
    claimed = client.model.lower()
    model_ids_lower = [m.lower() for m in models]

    # 精确匹配
    if claimed in model_ids_lower:
        return CheckResult(
            name="模型列表查询",
            score=0.3, confidence=0.4, cost_tokens=0,
            details=f"声称模型 '{client.model}' 在列表中找到（但列表可能是假的）",
            passed=True
        )

    # 模糊匹配（检查是否包含关键词）
    claimed_parts = claimed.split("/")
    for part in claimed_parts:
        if part in model_ids_lower:
            return CheckResult(
                name="模型列表查询",
                score=0.2, confidence=0.3, cost_tokens=0,
                details=f"部分匹配: 列表中存在 '{part}'",
                passed=True
            )

    # 不在列表中
    # 显示部分列表供参考
    sample = models[:15]
    return CheckResult(
        name="模型列表查询",
        score=-0.5, confidence=0.5, cost_tokens=0,
        details=f"声称模型 '{client.model}' 不在模型列表中。\n  列表示例: {sample}",
        passed=False
    )


def check_response_model_field(client: APIClient) -> CheckResult:
    """检测2: 检查响应中的 model 字段（低成本）"""
    resp = client.chat(
        messages=[{"role": "user", "content": "Say hello in one word."}],
        max_tokens=10
    )

    if not resp.success:
        return CheckResult(
            name="响应 model 字段",
            score=0, confidence=0.1,
            cost_tokens=resp.usage.total_tokens if resp.usage else 0,
            details=f"请求失败: {resp.error}",
            passed=None
        )

    claimed = client.model.lower()
    actual = (resp.model_field or "").lower()

    # 精确匹配
    if actual == claimed:
        return CheckResult(
            name="响应 model 字段",
            score=0.5, confidence=0.6,
            cost_tokens=resp.usage.total_tokens if resp.usage else 0,
            details=f"响应 model 字段与声称一致: {resp.model_field}",
            passed=True
        )

    # 检查是否是已知的假模型
    for pattern in FAKE_MODEL_PATTERNS:
        if pattern in actual:
            return CheckResult(
                name="响应 model 字段",
                score=-0.8, confidence=0.8,
                cost_tokens=resp.usage.total_tokens if resp.usage else 0,
                details=f"响应 model 字段包含已知假模型模式 '{pattern}': {resp.model_field}",
                passed=False
            )

    # 检查是否是已知开源模型
    for oss in KNOWN_OPEN_SOURCE_MODELS:
        if oss in actual:
            return CheckResult(
                name="响应 model 字段",
                score=-0.7, confidence=0.7,
                cost_tokens=resp.usage.total_tokens if resp.usage else 0,
                details=f"响应 model 字段指向开源模型 '{oss}': {resp.model_field}",
                passed=False
            )

    # 检查是否是真实模型（但名称不同）
    real_all = REAL_OPENAI_MODELS | REAL_ANTHROPIC_MODELS | REAL_GOOGLE_MODELS
    for real in real_all:
        if real.lower() in actual:
            return CheckResult(
                name="响应 model 字段",
                score=0.6, confidence=0.7,
                cost_tokens=resp.usage.total_tokens if resp.usage else 0,
                details=f"响应 model 字段包含真实模型 '{real}': {resp.model_field}\n  注意: 可能是同系列不同版本",
                passed=True
            )

    # 完全不匹配
    return CheckResult(
        name="响应 model 字段",
        score=-0.6, confidence=0.6,
        cost_tokens=resp.usage.total_tokens if resp.usage else 0,
        details=f"不匹配! 声称: {client.model}, 实际响应: {resp.model_field}",
        passed=False
    )


def check_response_headers(client: APIClient) -> CheckResult:
    """检测3: 分析响应头中的线索（免费）"""
    resp = client.chat(
        messages=[{"role": "user", "content": "test"}],
        max_tokens=5
    )

    if not resp.success or not resp.headers:
        return CheckResult(
            name="响应头分析",
            score=0, confidence=0.1,
            cost_tokens=resp.usage.total_tokens if resp.usage else 0,
            details=f"无法获取响应头: {resp.error}",
            passed=None
        )

    headers = resp.headers
    clues = []

    # 检查已知提供商的特征
    for provider, patterns in PROVIDER_HEADER_PATTERNS.items():
        for key, value in headers.items():
            key_lower = key.lower()
            value_lower = value.lower() if isinstance(value, str) else ""
            for pattern in patterns:
                if pattern in key_lower or pattern in value_lower:
                    clues.append(f"{key}: {value} → 指向 {provider}")

    # OneAPI 特征
    if "x-oneapi-request-id" in headers:
        clues.append(f"x-oneapi-request-id 存在 → 使用 OneAPI 网关")

    # 检查 Server 字段
    server = headers.get("server", headers.get("Server", ""))
    if server:
        clues.append(f"Server: {server}")

    # 检查是否有 openai 特征
    has_openai = any("openai" in k.lower() or "openai" in str(v).lower()
                     for k, v in headers.items())

    if clues:
        clue_text = "\n  ".join(clues)
        # 判断是否泄露了非声称提供商的信息
        claimed_provider = _guess_provider(client.model)
        detected_provider = None
        for clue in clues:
            for p in PROVIDER_HEADER_PATTERNS:
                if p in clue.lower():
                    detected_provider = p

        if detected_provider and detected_provider != claimed_provider:
            return CheckResult(
                name="响应头分析",
                score=-0.4, confidence=0.5,
                cost_tokens=resp.usage.total_tokens if resp.usage else 0,
                details=f"响应头泄露线索:\n  {clue_text}\n  声称提供商: {claimed_provider}, 检测到: {detected_provider}",
                passed=False
            )
        else:
            return CheckResult(
                name="响应头分析",
                score=0.1, confidence=0.3,
                cost_tokens=resp.usage.total_tokens if resp.usage else 0,
                details=f"响应头线索:\n  {clue_text}",
                passed=None
            )
    else:
        return CheckResult(
            name="响应头分析",
            score=0, confidence=0.2,
            cost_tokens=resp.usage.total_tokens if resp.usage else 0,
            details="响应头中未发现明显提供商特征",
            passed=None
        )


def check_identity(client: APIClient) -> CheckResult:
    """检测4: 身份认知测试（低成本）"""
    resp = client.chat(
        messages=[{
            "role": "user",
            "content": "What is your exact model name and version? "
                       "What is your training data cutoff date? "
                       "Answer directly and be specific."
        }],
        max_tokens=150,
        temperature=0.1
    )

    if not resp.success:
        return CheckResult(
            name="身份认知测试",
            score=0, confidence=0.1,
            cost_tokens=resp.usage.total_tokens if resp.usage else 0,
            details=f"请求失败: {resp.error}",
            passed=None
        )

    content = (resp.content or "").lower()
    claimed = client.model.lower()

    # 检查回复是否与声称一致
    evidence_for = 0
    evidence_against = 0
    notes = []

    # GPT 系列自报
    if any(x in content for x in ["gpt-4o", "gpt-4 turbo", "gpt-5"]):
        if "gpt" in claimed:
            evidence_for += 0.3
            notes.append("自报为 GPT 系列")
        else:
            evidence_against += 0.3
            notes.append("自报为 GPT 系列，但声称不是")

    # Claude 系列自报
    if any(x in content for x in ["claude", "anthropic"]):
        if "claude" in claimed:
            evidence_for += 0.3
            notes.append("自报为 Claude 系列")
        else:
            evidence_against += 0.3
            notes.append("自报为 Claude 系列，但声称不是")

    # Gemini 系列自报
    if any(x in content for x in ["gemini", "google"]):
        if "gemini" in claimed:
            evidence_for += 0.3
            notes.append("自报为 Gemini 系列")
        else:
            evidence_against += 0.3
            notes.append("自报为 Gemini 系列，但声称不是")

    # 国内模型自报
    if any(x in content for x in ["千问", "qwen", "通义", "deepseek", "豆包", "doubao"]):
        evidence_against += 0.5
        notes.append("自报为国内模型（与声称不符）")

    # 拒绝回答（可能是有系统提示约束）
    if any(x in content for x in ["cannot", "unable", "don't have access", "无法确认"]):
        notes.append("拒绝确认自身身份（可能有系统提示约束）")
        # 这种情况不确定性高
        return CheckResult(
            name="身份认知测试",
            score=0, confidence=0.2,
            cost_tokens=resp.usage.total_tokens if resp.usage else 0,
            details=f"模型拒绝确认身份。\n  回复: {(resp.content or '(empty)')[:200]}\n  推测: 可能有系统提示覆盖",
            passed=None
        )

    total = evidence_for - evidence_against
    note_text = "\n  ".join(notes) if notes else "未发现明确线索"

    return CheckResult(
        name="身份认知测试",
        score=max(-1, min(1, total)),
        confidence=min(abs(total), 0.6) if total != 0 else 0.2,
        cost_tokens=resp.usage.total_tokens if resp.usage else 0,
        details=f"线索: {note_text}\n  回复摘要: {(resp.content or '(empty)')[:200]}",
        passed=True if total > 0 else (False if total < 0 else None)
    )


def check_knowledge_cutoff(client: APIClient) -> CheckResult:
    """检测5: 知识截止日期测试（低成本）"""
    resp = client.chat(
        messages=[{
            "role": "user",
            "content": "Who won the 2024 US Presidential Election? "
                       "Answer in one sentence."
        }],
        max_tokens=80,
        temperature=0.1
    )

    if not resp.success:
        return CheckResult(
            name="知识截止测试",
            score=0, confidence=0.1,
            cost_tokens=resp.usage.total_tokens if resp.usage else 0,
            details=f"请求失败: {resp.error}",
            passed=None
        )

    content = (resp.content or "").lower()

    # 判断知识截止
    knows_2024 = any(x in content for x in [
        "trump", "特朗普", "harris", "哈里斯",
        "won", "won the election", "elected",
        "president-elect", "47th"
    ])

    # 如果声称的模型应该知道2024事件但不知道
    claimed = client.model.lower()
    should_know = any(x in claimed for x in [
        "gpt-4o", "gpt-5", "claude-3", "claude-opus", "claude-sonnet",
        "gemini-2", "gemini-1.5"
    ])

    if knows_2024:
        return CheckResult(
            name="知识截止测试",
            score=0.3 if should_know else 0.1,
            confidence=0.4,
            cost_tokens=resp.usage.total_tokens if resp.usage else 0,
            details=f"知道 2024 美国大选结果（知识截止 >= 2024）\n  回复: {(resp.content or '(empty)')[:150]}",
            passed=True if should_know else None
        )
    else:
        # 不知道2024事件 → 可能是较旧的模型
        return CheckResult(
            name="知识截止测试",
            score=-0.3 if should_know else 0,
            confidence=0.4,
            cost_tokens=resp.usage.total_tokens if resp.usage else 0,
            details=f"不知道 2024 美国大选结果（知识截止 < 2024）\n  回复: {(resp.content or '(empty)')[:150]}",
            passed=False if should_know else None
        )


def check_reasoning(client: APIClient) -> CheckResult:
    """检测6: 推理能力测试（中等成本）"""
    resp = client.chat(
        messages=[{
            "role": "user",
            "content": "Think step by step: A bat and a ball cost $1.10 total. "
                       "The bat costs $1 more than the ball. "
                       "How much does the ball cost? Give the final answer as a number."
        }],
        max_tokens=200,
        temperature=0.1
    )

    if not resp.success:
        return CheckResult(
            name="推理能力测试",
            score=0, confidence=0.1,
            cost_tokens=resp.usage.total_tokens if resp.usage else 0,
            details=f"请求失败: {resp.error}",
            passed=None
        )

    content = (resp.content or "").lower()

    # 正确答案是 $0.05
    has_correct = "0.05" in content or "$0.05" in content or "5 cents" in content or "5¢" in content
    has_wrong = "0.10" in content or "$0.10" in content or "10 cents" in content

    if has_correct:
        score = 0.5
        details = f"推理正确（$0.05）\n  回复: {(resp.content or '(empty)')[:200]}"
    elif has_wrong:
        score = -0.2
        details = f"推理错误（回答 $0.10）\n  回复: {(resp.content or '(empty)')[:200]}"
    else:
        score = 0
        details = f"未给出明确答案\n  回复: {(resp.content or '(empty)')[:200]}"

    return CheckResult(
        name="推理能力测试",
        score=score,
        confidence=0.4,
        cost_tokens=resp.usage.total_tokens if resp.usage else 0,
        details=details,
        passed=True if has_correct else (False if has_wrong else None)
    )


def _guess_provider(model_name: str) -> str:
    """根据模型名猜测提供商"""
    m = model_name.lower()
    if any(x in m for x in ["gpt", "o3", "o4"]):
        return "openai"
    if any(x in m for x in ["claude", "sonnet", "opus", "haiku"]):
        return "anthropic"
    if any(x in m for x in ["gemini", "gemma"]):
        return "google"
    if any(x in m for x in ["qwen", "glm", "deepseek"]):
        return "alibaba/deepseek"
    return "unknown"


# V1 检测清单（按成本从低到高排列）
V1_CHECKS = [
    ("模型列表查询", check_models_list, "FREE"),
    ("响应头分析", check_response_headers, "FREE"),
    ("响应 model 字段", check_response_model_field, "~10 tok"),
    ("身份认知测试", check_identity, "~50 tok"),
    ("知识截止测试", check_knowledge_cutoff, "~50 tok"),
    ("推理能力测试", check_reasoning, "~150 tok"),
]
