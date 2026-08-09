"""
OpenAI 协议检测器配置（v2.2）

9 项检测器权重表（和=1.0）：
  basic_request      0.15  AUTHENTICITY
  model_consistency  0.15  AUTHENTICITY
  function_calling   0.15  CAPABILITY
  long_context       0.15  CAPABILITY (full + --long-context only)
  protocol           0.10  COMPLIANCE
  integrity          0.08  COMPLIANCE
  structured_output  0.10  CAPABILITY
  token_billing      0.07  COMPLIANCE
  billing_integrity  0.05  COMPLIANCE  (v2.2 新增，计费审计)
"""

from src.core.models import DetectorCategory

# 检测器权重
WEIGHTS = {
    "basic_request": 0.15,
    "model_consistency": 0.15,
    "function_calling": 0.15,
    "long_context": 0.15,
    "protocol": 0.10,
    "integrity": 0.08,
    "structured_output": 0.10,
    "token_billing": 0.07,
    "billing_integrity": 0.05,
}

# 检测器分类
CATEGORIES = {
    "basic_request": DetectorCategory.AUTHENTICITY,
    "model_consistency": DetectorCategory.AUTHENTICITY,
    "function_calling": DetectorCategory.CAPABILITY,
    "long_context": DetectorCategory.CAPABILITY,
    "protocol": DetectorCategory.COMPLIANCE,
    "integrity": DetectorCategory.COMPLIANCE,
    "structured_output": DetectorCategory.CAPABILITY,
    "token_billing": DetectorCategory.COMPLIANCE,
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

    gated_detectors = {"long_context"}
    _check_mode_list("quick", QUICK_DETECTORS, errors)
    _check_mode_list("standard", STANDARD_DETECTORS, errors)
    _check_mode_list("full", FULL_DETECTORS, errors, gated_detectors)

    if errors:
        raise RuntimeError(
            "OpenAI 检测器配置校验失败:\n" + "\n".join(f"  - {e}" for e in errors)
        )



# 检测器运行模式
DETECTOR_MODES = {
    "basic_request": ["quick", "standard", "full"],

    "model_consistency": ["quick", "standard", "full"],
    "function_calling": ["standard", "full"],
    "long_context": ["full"],  # 仅 full + --long-context
    "protocol": ["quick", "standard", "full"],
    "integrity": ["standard", "full"],
    "structured_output": ["full"],
    "token_billing": ["standard", "full"],
    "billing_integrity": ["standard", "full"],
}

# quick 模式检测器列表
QUICK_DETECTORS = ["basic_request", "model_consistency", "protocol"]

# standard 模式检测器列表
STANDARD_DETECTORS = QUICK_DETECTORS + ["function_calling", "integrity", "token_billing", "billing_integrity"]

# full 模式检测器列表
FULL_DETECTORS = STANDARD_DETECTORS + ["structured_output"]  # long_context 单独控制
