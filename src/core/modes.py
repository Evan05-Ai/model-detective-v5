"""
运行模式定义

quick:    ~6 请求, ~15s  - 核心真伪检测
standard: ~12 请求, ~40s - 真伪+能力+合规
full:     ~13+ 请求, ~70s+ - 全部检测器 + 可选长上下文
"""

from .models import RunMode


# 各模式 token 预算上限
TOKEN_BUDGETS = {
    RunMode.QUICK: 5_000,      # v2.8: 提升至 5,000
    RunMode.STANDARD: 100_000,  # v2.8: 提升至 100,000，避免预算耗尽
    RunMode.FULL: 200_000,     # v2.8: 提升至 200,000
}

# 各模式包含的检测器（按协议分组后由各协议 config 定义具体列表）
MODE_DETECTOR_LEVELS = {
    RunMode.QUICK: "quick",
    RunMode.STANDARD: "standard",
    RunMode.FULL: "full",
}


def get_token_budget(mode: RunMode) -> int:
    """获取模式的 token 预算上限"""
    return TOKEN_BUDGETS.get(mode, TOKEN_BUDGETS[RunMode.STANDARD])


def should_run_detector(detector_modes: list[str], mode: RunMode) -> bool:
    """判断检测器是否在当前模式下运行"""
    level = MODE_DETECTOR_LEVELS.get(mode, "standard")
    return level in detector_modes


# 长上下文探针的渐进式层级
LONG_CONTEXT_PROBES = [
    {"name": "32k", "input_tokens": 32_000, "needle": "The secret code is: ZEPHYR-7X-2024"},
    {"name": "100k", "input_tokens": 100_000, "needle": "The secret code is: AURORA-3K-2025"},
    {"name": "200k", "input_tokens": 200_000, "needle": "The secret code is: NEBULA-9Q-2026"},
]

# 长上下文预估成本（按 GPT-4o 定价 $2.5/1M input）
def estimate_long_context_cost() -> float:
    """预估长上下文检测的总成本（USD）"""
    total_tokens = sum(p["input_tokens"] for p in LONG_CONTEXT_PROBES)
    return total_tokens * 2.5 / 1_000_000
