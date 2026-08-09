"""OpenAI 协议检测器注册"""

from typing import List
from src.core.detector_base import ActiveDetector, PassiveDetector
from .basic_request import BasicRequestDetector
from .model_consistency import ModelConsistencyDetector
from .function_calling import FunctionCallingDetector
from .structured_output import StructuredOutputDetector
from .protocol import ProtocolDetector
from .integrity import IntegrityDetector
from .token_billing import TokenBillingDetector
from .long_context import LongContextDetector
from .billing_integrity import BillingIntegrityDetector


def build_active_detectors(long_context: bool = False) -> List[ActiveDetector]:
    """构建所有 ActiveDetector"""
    detectors = [
        BasicRequestDetector(),
        ModelConsistencyDetector(),
        FunctionCallingDetector(),
        StructuredOutputDetector(),
        ProtocolDetector(),
        TokenBillingDetector(),
        BillingIntegrityDetector(),
    ]
    if long_context:
        detectors.append(LongContextDetector())
    return detectors


def build_passive_detectors() -> List[PassiveDetector]:
    """构建所有 PassiveDetector"""
    return [
        IntegrityDetector(),
    ]
