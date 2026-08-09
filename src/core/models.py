"""
V2 数据模型 - 所有检测器、评分、报告共享的数据结构

这是接口先行的核心：先固定这些 dataclass，detectors 和 reports 才能并行开发。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Protocol(Enum):
    """支持的协议类型"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"


class IssueLevel(Enum):
    """问题严重级别（veridrop 四级分类 + v2.1 新增 MEDIUM）"""
    CRITICAL = "critical"   # 致命问题，锁定 verdict 上限
    MAJOR = "major"         # 重大问题
    MEDIUM = "medium"       # 中等问题（v2.1 新增，用于链路中转等非致命但需关注的情况）
    MINOR = "minor"         # 轻微问题
    OK = "ok"               # 无问题


class Verdict(Enum):
    """最终裁定级别"""
    PASSED_EXCELLENT = "passed_excellent"  # >= 85
    PASSED = "passed"                      # 70-84
    MARGINAL = "marginal"                  # 50-69
    FAILED = "failed"                      # < 50


class DetectorCategory(Enum):
    """检测器三维分类"""
    AUTHENTICITY = "authenticity"   # 真伪
    CAPABILITY = "capability"       # 能力
    COMPLIANCE = "compliance"       # 合规


class RunMode(Enum):
    """运行模式"""
    QUICK = "quick"         # ~6 请求, ~15s
    STANDARD = "standard"   # ~12 请求, ~40s
    FULL = "full"           # ~13+ 请求, ~70s+


class BackendSource(Enum):
    """推断的后端来源（v2.1 新增）"""
    ANTHROPIC_DIRECT = "anthropic_direct"   # Anthropic 原生 API
    BEDROCK_DIRECT = "bedrock_direct"       # AWS Bedrock 直连
    KIRO_PROXY = "kiro_proxy"               # Kiro (Amazon Q) 代理链路
    VERTEX_PROXY = "vertex_proxy"           # Google Vertex AI 代理链路
    UNKNOWN_PROXY = "unknown_proxy"         # 未知代理链路
    UNKNOWN = "unknown"                     # 无法判断


@dataclass
class Issue:
    """检测中发现的问题"""
    level: IssueLevel
    message: str
    detector_name: str = ""


@dataclass
class CheckResultV2:
    """单项检测结果（V2 体系，0-100 分）
    
    v2.6 新增置信度系统：
      - confidence: 0-1，表示检测结果的可信程度
      - confidence_reason: 解释置信度高低的原因
      
    置信度定义：
      - 1.0: 高置信度（如 thinking_signature 检测到有效签名）
      - 0.7-0.9: 中高置信度（如 identity 获得明确回答）
      - 0.4-0.6: 中等置信度（如 identity 被拒绝但获得部分信息）
      - 0.1-0.3: 低置信度（如 identity 全部被拒绝，或检测到异常）
      - 0.0: 无法判断（如请求失败）
    """
    name: str
    category: DetectorCategory
    score: float                        # 0-100
    weight: float                       # 权重，参与加权平均
    issues: list[Issue] = field(default_factory=list)
    cost_tokens: int = 0
    details: str = ""
    status: str = "pass"                # pass / fail / skip / error
    raw_response: Optional[dict] = None
    confidence: float = 1.0             # v2.6: 置信度 0-1
    confidence_reason: str = ""         # v2.6: 置信度说明

    @property
    def has_critical(self) -> bool:
        return any(i.level == IssueLevel.CRITICAL for i in self.issues)

    @property
    def effective(self) -> bool:
        """是否参与评分（仅 skip 不参与分母）

        v2.4 修复：error 状态参与评分（score=0），防止大量 error 导致
        总分虚高。只有 skip（预算耗尽、模式不匹配）才排除。
        """
        return self.status in ("pass", "fail", "error")
    
    @property
    def weighted_confidence_score(self) -> float:
        """v2.6: 加权置信度分数 = score * confidence
        
        用于在评分时考虑检测结果的可信度。
        例如：identity 检测被拒绝时，confidence=0.3，即使 score=35，
        实际影响评分的有效分数为 35 * 0.3 = 10.5
        """
        return self.score * self.confidence


@dataclass
class DetectionReport:
    """完整检测报告（v2.1 新增 backend_source）"""
    model: str
    protocol: Protocol
    mode: str
    degraded: bool                          # 是否降级到 OpenAI 兼容协议
    results: list[CheckResultV2]
    total_score: float                      # 加权总分 0-100
    verdict: Verdict
    authenticity_score: float               # 真伪维度分
    capability_score: float                 # 能力维度分
    compliance_score: float                 # 合规维度分
    total_tokens: int
    total_requests: int
    estimated_cost_usd: float
    has_critical: bool                      # 是否存在 critical issue
    backend_source: str = "unknown"         # 推断的后端来源（v2.1 新增）
    baseline_diff: Optional[dict] = None    # 基线对比差异
    duration_seconds: float = 0.0

    @property
    def exit_code(self) -> int:
        """V2 退出码：FAILED→1, MARGINAL→2, PASSED/PASSED_EXCELLENT→0"""
        if self.verdict == Verdict.FAILED:
            return 1
        elif self.verdict == Verdict.MARGINAL:
            return 2
        return 0
