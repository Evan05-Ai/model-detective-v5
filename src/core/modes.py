"""
运行模式定义

quick:    ~6 请求, ~15s  - 核心真伪检测
standard: ~12 请求, ~40s - 真伪+能力+合规
full:     ~13+ 请求, ~70s+ - 全部检测器 + 可选长上下文
"""

from .models import RunMode


# 各模式 token 预算上限（v3.0.3 起为"请求信封"口径：按我方实际发出的
# 请求内容估算，不受中转站上报数字影响，详见 base_client._add_envelope）
TOKEN_BUDGETS = {
    RunMode.QUICK: 5_000,
    RunMode.STANDARD: 100_000,
    RunMode.FULL: 200_000,
}

# v3.0.3: 钱包费用上限（USD）——按中转站上报口径 + 官方价折算的预估费用
# 兜底。设计原则"完成优先、披露成本"：诚实中转站一次 Standard 检测约
# $0.1，缓存密集中转站（Kiro 类）约 $1-2，固定开销大的站（beiluoxi 类，
# ~48k tokens/请求 × opus 定价）约 $10-11——这些都应该完整出报告，让
# billing_integrity 的"单请求固定开销"披露来说话，而不是半途砍掉检测。
# 只有上报离谱（>$15-20）才中止。用户若在乎成本，报告里的费用数字和
# 披露就是决策依据。
WALLET_COST_LIMITS = {
    RunMode.QUICK: 5.0,
    RunMode.STANDARD: 15.0,
    RunMode.FULL: 30.0,
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


def get_wallet_limit(mode: RunMode) -> float:
    """获取模式的预估费用止损上限（USD）"""
    return WALLET_COST_LIMITS.get(mode, WALLET_COST_LIMITS[RunMode.STANDARD])


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
