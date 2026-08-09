"""
价格数据库 + 中转站价格对比

借鉴 hvoy.ai 的实用性维度：检测到假模型时显示真实价值
"""

from src.signatures import OFFICIAL_PRICING


def get_official_price(model: str) -> dict:
    """获取模型官方定价"""
    m = model.lower()
    # 精确匹配
    if m in OFFICIAL_PRICING:
        return OFFICIAL_PRICING[m]

    # 前缀模糊匹配：只允许 key 是 model 的前缀（避免 claude-opus-4 匹配到 claude-opus-4-5）
    best_key = None
    best_len = 0
    for key in OFFICIAL_PRICING:
        if m.startswith(key) and len(key) > best_len:
            best_key = key
            best_len = len(key)
    if best_key:
        return OFFICIAL_PRICING[best_key]

    return {"input": None, "output": None}


def compare_price(model: str, proxy_price: dict = None) -> dict:
    """
    对比官方价格与中转站价格

    Args:
        model: 模型名
        proxy_price: 中转站价格 {"input": float, "output": float}（每 1M tokens）

    Returns:
        {
            "official": {"input": float, "output": float},
            "proxy": {"input": float, "output": float},
            "input_discount": float,   # 输入折扣率 (0-1)
            "output_discount": float,  # 输出折扣率
            "verdict": str,            # 价格评估
        }
    """
    official = get_official_price(model)

    if not proxy_price:
        return {
            "official": official,
            "proxy": None,
            "verdict": "未提供中转站价格",
        }

    result = {
        "official": official,
        "proxy": proxy_price,
    }

    if official.get("input") and proxy_price.get("input"):
        result["input_discount"] = proxy_price["input"] / official["input"]
    if official.get("output") and proxy_price.get("output"):
        result["output_discount"] = proxy_price["output"] / official["output"]

    # 评估
    input_disc = result.get("input_discount", 1.0)
    output_disc = result.get("output_discount", 1.0)
    avg_disc = (input_disc + output_disc) / 2

    if avg_disc < 0.3:
        result["verdict"] = "价格异常低，可能是假模型或开源模型冒充"
    elif avg_disc < 0.5:
        result["verdict"] = "价格显著低于官方，需警惕"
    elif avg_disc < 0.8:
        result["verdict"] = "价格低于官方，可能是代理商折扣"
    elif avg_disc <= 1.2:
        result["verdict"] = "价格接近官方，合理"
    else:
        result["verdict"] = "价格高于官方，不建议使用"

    return result


def estimate_real_value(detected_model: str, claimed_model: str) -> dict:
    """
    检测到假模型时，估算真实价值

    Args:
        detected_model: 实际检测到的模型
        claimed_model: 声称的模型
    """
    claimed_price = get_official_price(claimed_model)
    real_price = get_official_price(detected_model)

    if claimed_price.get("input") and real_price.get("input"):
        value_ratio = real_price["input"] / claimed_price["input"]
    else:
        value_ratio = None

    return {
        "claimed_model": claimed_model,
        "claimed_price": claimed_price,
        "detected_model": detected_model,
        "real_price": real_price,
        "value_ratio": value_ratio,
        "verdict": f"你花了 {claimed_model} 的价格，买到的是 {detected_model} 的服务" if value_ratio else "无法估算",
    }
