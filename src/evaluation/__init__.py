"""
Evaluation Module - 模型能力测评模块

提供模型能力标准化测评功能，支持：
- 多模型批量测评
- 多维度评分（基础语言/技术/高级认知/实用/边界）
- 实时进度回调
- JSON/HTML 报告导出
"""

from __future__ import annotations

from .eval_engine import (
    EvaluationEngine,
    EvalQuestion,
    EvalResult,
    EvalDimension,
    EvalDifficulty,
    BASIC_LANGUAGE_QUESTIONS,
    TECHNICAL_QUESTIONS,
    ADVANCED_QUESTIONS,
    PRACTICAL_QUESTIONS,
    BOUNDARY_QUESTIONS,
    QUICK_QUESTIONS,
    STANDARD_QUESTIONS,
    score_answer,
)

__all__ = [
    "EvaluationEngine",
    "EvalQuestion",
    "EvalResult",
    "EvalDimension",
    "EvalDifficulty",
    "BASIC_LANGUAGE_QUESTIONS",
    "TECHNICAL_QUESTIONS",
    "ADVANCED_QUESTIONS",
    "PRACTICAL_QUESTIONS",
    "BOUNDARY_QUESTIONS",
    "QUICK_QUESTIONS",
    "STANDARD_QUESTIONS",
    "score_answer",
]
