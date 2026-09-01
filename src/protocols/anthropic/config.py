"""
Anthropic 协议检测器配置（v2.6）

14 项检测器权重表（v2.6 调整后）：
  thinking_signature    0.25  AUTHENTICITY  (加密级，核心)
  identity              0.12  AUTHENTICITY  (v2.6: 0.10 -> 0.12)
  consistency           0.10  AUTHENTICITY
  behavioral_signature  0.04  AUTHENTICITY  (v2.6: 0.08 -> 0.04，降低过拟合风险)
  knowledge             0.06  AUTHENTICITY  (v2.6: 0.07 -> 0.06)
  protocol              0.06  COMPLIANCE
  integrity             0.08  COMPLIANCE    (v2.6: 0.06 -> 0.08，被动观察更客观)
  billing_integrity     0.05  COMPLIANCE    (v2.2 新增，计费审计)
  function_calling      0.06  CAPABILITY
  message_id            0.03  COMPLIANCE
  token_usage           0.02  COMPLIANCE
  structured_output     0.05  CAPABILITY
  pdf                   0.05  CAPABILITY
  long_context          0.03  CAPABILITY    (v2.6: 0.02 -> 0.03，仅 full 模式)
  ────────────────────────────────────
                         1.00  合计

v2.6 变更：
  - identity 0.10 -> 0.12（身份认知更重要）
  - behavioral_signature 0.08 -> 0.04（降低过拟合风险高的检测器权重）
  - knowledge 0.07 -> 0.06
  - integrity 0.06 -> 0.08（被动观察更客观）
  - long_context 0.02 -> 0.03（长上下文能力重要性提升）

v2.2 变更：
  - 新增 billing_integrity 0.05（计费完整性检测）
  - protocol 0.08 → 0.06
  - message_id 0.05 → 0.03
  - token_usage 0.03 → 0.02
"""

from src.core.models import DetectorCategory

WEIGHTS = {
    "thinking_signature": 0.25,
    "identity": 0.12,           # v2.6: 0.10 -> 0.12，身份认知更重要
    "consistency": 0.10,
    "behavioral_signature": 0.04,  # v2.6: 0.08 -> 0.04，降低过拟合风险高的检测器权重
    "knowledge": 0.06,          # v2.6: 0.07 -> 0.06
    "protocol": 0.06,
    "integrity": 0.08,          # v2.6: 0.06 -> 0.08，被动观察更客观
    "billing_integrity": 0.05,
    "function_calling": 0.06,
    "message_id": 0.03,
    "token_usage": 0.02,
    "structured_output": 0.05,
    "pdf": 0.05,
    "long_context": 0.03,       # v2.6: 0.02 -> 0.03，长上下文能力重要性提升
}

CATEGORIES = {
    "thinking_signature": DetectorCategory.AUTHENTICITY,
    "identity": DetectorCategory.AUTHENTICITY,
    "consistency": DetectorCategory.AUTHENTICITY,
    "behavioral_signature": DetectorCategory.AUTHENTICITY,
    "knowledge": DetectorCategory.AUTHENTICITY,
    "protocol": DetectorCategory.COMPLIANCE,
    "integrity": DetectorCategory.COMPLIANCE,
    "billing_integrity": DetectorCategory.COMPLIANCE,
    "function_calling": DetectorCategory.CAPABILITY,
    "message_id": DetectorCategory.COMPLIANCE,
    "token_usage": DetectorCategory.COMPLIANCE,
    "structured_output": DetectorCategory.CAPABILITY,
    "pdf": DetectorCategory.CAPABILITY,
    "long_context": DetectorCategory.CAPABILITY,
}


def _expected_detectors_for_mode(mode: str, gated_detectors: set[str] | None = None) -> set[str]:
    """从 DETECTOR_MODES 推导指定模式应启用的检测器。"""
    gated_detectors = gated_detectors or set()
    return {
        name
        for name, modes in DETECTOR_MODES.items()
        if mode in modes and name not in gated_detectors
    }


def _check_mode_list(mode: str, configured: list[str], errors: list[str], gated_detectors: set[str] | None = None) -> None:
    """校验显式模式列表与 DETECTOR_MODES 推导结果一致。"""
    expected = _expected_detectors_for_mode(mode, gated_detectors)
    actual = set(configured)
    missing = expected - actual
    extra = actual - expected
    if missing:
        errors.append(f"{mode} 模式列表缺少: {missing}")
    if extra:
        errors.append(f"{mode} 模式列表多余: {extra}")


def validate_weights() -> None:
    """启动时校验检测器配置一致性。"""
    in_weights = set(WEIGHTS.keys())
    in_categories = set(CATEGORIES.keys())
    in_modes = set(DETECTOR_MODES.keys())

    missing_in_weights = in_categories - in_weights
    missing_in_categories = in_weights - in_categories
    missing_in_modes = in_weights - in_modes
    extra_modes = in_modes - in_weights
    weight_sum = sum(WEIGHTS.values())

    errors = []
    if missing_in_weights:
        errors.append(f"在 CATEGORIES 中但不在 WEIGHTS 中: {missing_in_weights}")
    if missing_in_categories:
        errors.append(f"在 WEIGHTS 中但不在 CATEGORIES 中: {missing_in_categories}")
    if missing_in_modes:
        errors.append(f"在 WEIGHTS 中但不在 DETECTOR_MODES 中: {missing_in_modes}")
    if extra_modes:
        errors.append(f"在 DETECTOR_MODES 中但不在 WEIGHTS 中: {extra_modes}")
    if abs(weight_sum - 1.0) > 0.001:
        errors.append(f"权重和={weight_sum:.3f}，应=1.0")

    gated_detectors = {"long_context"}
    _check_mode_list("quick", QUICK_DETECTORS, errors)
    _check_mode_list("standard", STANDARD_DETECTORS, errors)
    _check_mode_list("full", FULL_DETECTORS, errors, gated_detectors)

    if errors:
        raise RuntimeError(
            f"Anthropic 检测器配置校验失败:\n" + "\n".join(f"  - {e}" for e in errors)
        )

DETECTOR_MODES = {
    "thinking_signature": ["quick", "standard", "full"],

    "identity": ["quick", "standard", "full"],
    "protocol": ["quick", "standard", "full"],
    "consistency": ["standard", "full"],
    "behavioral_signature": ["standard", "full"],
    "knowledge": ["standard", "full"],
    "integrity": ["standard", "full"],
    "billing_integrity": ["standard", "full"],
    "function_calling": ["standard", "full"],
    "message_id": ["standard", "full"],
    "token_usage": ["standard", "full"],
    "structured_output": ["full"],
    "pdf": ["full"],
    "long_context": ["full"],
}

QUICK_DETECTORS = ["thinking_signature", "identity", "protocol"]

STANDARD_DETECTORS = QUICK_DETECTORS + [
    "consistency", "behavioral_signature", "knowledge",
    "integrity", "billing_integrity", "function_calling", "message_id", "token_usage",
]

FULL_DETECTORS = STANDARD_DETECTORS + ["structured_output", "pdf"]  # long_context 单独控制

