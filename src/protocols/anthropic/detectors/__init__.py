"""Anthropic 协议检测器注册"""

from typing import List
from src.core.detector_base import ActiveDetector, PassiveDetector
from .identity import IdentityDetector
from .behavioral_signature import BehavioralSignatureDetector
from .thinking_signature import ThinkingSignatureDetector
from .consistency import ConsistencyDetector
from .knowledge import KnowledgeDetector
from .pdf import PDFDetector
from .structured_output import StructuredOutputDetector
from .function_calling import FunctionCallingDetector
from .protocol import ProtocolDetector
from .integrity import IntegrityDetector
from .message_id import MessageIdDetector
from .token_usage import TokenUsageDetector
from .long_context import LongContextDetector
from .billing_integrity import BillingIntegrityDetector


def build_active_detectors(long_context: bool = False) -> List[ActiveDetector]:
    """构建所有 ActiveDetector"""
    detectors: List[ActiveDetector] = [
        IdentityDetector(),
        ThinkingSignatureDetector(),
        BehavioralSignatureDetector(),
        ConsistencyDetector(),
        KnowledgeDetector(),
        ProtocolDetector(),
        FunctionCallingDetector(),
        StructuredOutputDetector(),
        PDFDetector(),
        MessageIdDetector(),
        TokenUsageDetector(),
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
