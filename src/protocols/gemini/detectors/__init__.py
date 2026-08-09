"""Gemini 协议检测器注册"""

from typing import List
from src.core.detector_base import ActiveDetector, PassiveDetector
from .basic_request import BasicRequestDetector
from .model_info import ModelInfoDetector
from .consistency import ConsistencyDetector  # v2.7 新增
from .function_calling import FunctionCallingDetector
from .structured_output import StructuredOutputDetector
from .protocol import ProtocolDetector
from .integrity import IntegrityDetector
from .token_usage import TokenUsageDetector
from .billing_integrity import BillingIntegrityDetector


def build_active_detectors(long_context: bool = False) -> List[ActiveDetector]:
    """构建所有 ActiveDetector"""
    return [
        BasicRequestDetector(),
        ModelInfoDetector(),
        ConsistencyDetector(),  # v2.7 新增
        FunctionCallingDetector(),
        StructuredOutputDetector(),
        ProtocolDetector(),
        TokenUsageDetector(),
        BillingIntegrityDetector(),
    ]


def build_passive_detectors() -> List[PassiveDetector]:
    """构建所有 PassiveDetector"""
    return [
        IntegrityDetector(),
    ]
