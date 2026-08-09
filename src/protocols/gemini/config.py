"""
Gemini 协议检测器配置

9 项检测器权重表（和=1.0）：
  basic_request      0.16  AUTHENTICITY
  model_info         0.14  AUTHENTICITY
  consistency        0.10  AUTHENTICITY  (v2.7 新增)
  function_calling   0.14  CAPABILITY
  structured_output  0.11  CAPABILITY
  protocol           0.10  COMPLIANCE
  integrity          0.08  COMPLIANCE
  token_usage        0.06  COMPLIANCE
  billing_integrity  0.11  COMPLIANCE
"""

from src.core.models import DetectorCategory

WEIGHTS = {
    "basic_request": 0.16,
    "model_info": 0.14,
    "consistency": 0.10,          # v2.7 新增
    "function_calling": 0.14,     # v2.7: 0.18 -> 0.14
    "structured_output": 0.11,    # v2.7: 0.15 -> 0.11
    "protocol": 0.10,
    "integrity": 0.08,
    "token_usage": 0.06,
    "billing_integrity": 0.11,   # v2.7: 0.13 -> 0.11
}

CATEGORIES = {
    "basic_request": DetectorCategory.AUTHENTICITY,
    "model_info": DetectorCategory.AUTHENTICITY,
    "consistency": DetectorCategory.AUTHENTICITY,  # v2.7 新增
    "function_calling": DetectorCategory.CAPABILITY,
    "structured_output": DetectorCategory.CAPABILITY,
    "protocol": DetectorCategory.COMPLIANCE,
    "integrity": DetectorCategory.COMPLIANCE,
    "token_usage": DetectorCategory.COMPLIANCE,
    "billing_integrity": DetectorCategory.COMPLIANCE,
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

    errors = []
    missing_in_weights = in_categories - in_weights
    missing_in_categories = in_weights - in_categories
    missing_in_modes = in_weights - in_modes
    extra_modes = in_modes - in_weights
    weight_sum = sum(WEIGHTS.values())

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

    _check_mode_list("quick", QUICK_DETECTORS, errors)
    _check_mode_list("standard", STANDARD_DETECTORS, errors)
    _check_mode_list("full", FULL_DETECTORS, errors)

    if errors:
        raise RuntimeError(
            "Gemini 检测器配置校验失败:\n" + "\n".join(f"  - {e}" for e in errors)
        )



DETECTOR_MODES = {
    "basic_request": ["quick", "standard", "full"],

    "model_info": ["quick", "standard", "full"],
    "protocol": ["quick", "standard", "full"],
    "consistency": ["standard", "full"],  # v2.7 新增
    "function_calling": ["standard", "full"],
    "structured_output": ["standard", "full"],
    "integrity": ["standard", "full"],
    "token_usage": ["standard", "full"],
    "billing_integrity": ["standard", "full"],
}

QUICK_DETECTORS = ["basic_request", "model_info", "protocol"]

STANDARD_DETECTORS = QUICK_DETECTORS + [
    "consistency", "function_calling", "structured_output", "integrity", "token_usage",
    "billing_integrity",
]

FULL_DETECTORS = STANDARD_DETECTORS  # Gemini 无额外 full 检测器
