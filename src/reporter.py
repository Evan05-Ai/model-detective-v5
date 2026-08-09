"""
终端输出美化 - 彩色结果展示
"""

from typing import List
from .checks import CheckResult


# ANSI 颜色
class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    RED     = "\033[91m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    BLUE    = "\033[94m"
    CYAN    = "\033[96m"
    WHITE   = "\033[97m"
    BG_RED  = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"


def print_header(base_url: str, model: str, api_key: str):
    """打印检测头部"""
    masked_key = api_key[:8] + "..." + api_key[-4:] if len(api_key) > 12 else "***"
    print(f"""
{C.BOLD}{C.CYAN}+----------------------------------------------------------+
|           [SEARCH] Model Detective v0.1                  |
|           Third-party API Relay Model Detection          |
+----------------------------------------------------------+{C.RESET}

  {C.DIM}Base URL:{C.RESET}  {base_url}
  {C.DIM}Model:{C.RESET}     {C.BOLD}{model}{C.RESET}
  {C.DIM}API Key:{C.RESET}   {masked_key}
""")


def print_check_result(result: CheckResult, index: int):
    """打印单项检测结果"""
    # 状态图标
    if result.passed is True:
        icon = f"{C.GREEN}[PASS]{C.RESET}"
    elif result.passed is False:
        icon = f"{C.RED}[FAIL]{C.RESET}"
    else:
        icon = f"{C.YELLOW}[?]   {C.RESET}"

    # 分数颜色
    if result.score > 0:
        score_color = C.GREEN
    elif result.score < 0:
        score_color = C.RED
    else:
        score_color = C.DIM

    print(f"  {C.DIM}[{index}]{C.RESET} {icon} {C.BOLD}{result.name}{C.RESET}  "
          f"{C.DIM}({result.cost_label}){C.RESET}  "
          f"Score: {score_color}{result.score:+.1f}{C.RESET}  "
          f"Conf: {result.confidence:.0%}")

    # 详细信息（缩进显示）
    for line in result.details.split("\n"):
        print(f"       {C.DIM}{line}{C.RESET}")
    print()


def print_verdict(score: float, confidence: float, total_tokens: int,
                  total_requests: int, model: str):
    """打印最终裁定"""
    # 裁定级别
    if score > 0.3:
        verdict = f"{C.GREEN}[PASS] Likely genuine model{C.RESET}"
        verdict_detail = "Multiple evidence supports the claimed model"
    elif score > 0:
        verdict = f"{C.YELLOW}[!]  Uncertain{C.RESET}"
        verdict_detail = "Insufficient evidence, more tests recommended"
    elif score > -0.3:
        verdict = f"{C.YELLOW}[!]  Suspicious{C.RESET}"
        verdict_detail = "Inconsistent evidence detected, proceed with caution"
    else:
        verdict = f"{C.RED}[FAIL] Likely fake model{C.RESET}"
        verdict_detail = "Multiple evidence indicates this is not the claimed model"

    print(f"""{C.BOLD}{C.CYAN}+----------------------------------------------------------+
|                     [REPORT] Final Verdict               |
+----------------------------------------------------------+{C.RESET}

  {C.BOLD}Model:{C.RESET}    {model}
  {C.BOLD}Verdict:{C.RESET}  {verdict}
  {C.BOLD}Detail:{C.RESET}   {verdict_detail}
  {C.BOLD}Score:{C.RESET}    {score:+.2f}  (range -1 ~ +1)
  {C.BOLD}Conf:{C.RESET}      {confidence:.0%}

  {C.DIM}--- Cost Summary ---{C.RESET}
  {C.DIM}Requests:{C.RESET}   {total_requests}
  {C.DIM}Tokens:{C.RESET}     {total_tokens}
  {C.DIM}Est. Cost:{C.RESET}  ~${total_tokens * 2.5 / 1_000_000:.4f} USD

""")


def print_summary_table(results: List[CheckResult]):
    """打印汇总表格"""
    print(f"  {C.BOLD}{'Check':<16} {'Result':<8} {'Score':<8} {'Cost':<10}{C.RESET}")
    print(f"  {'-' * 52}")

    for r in results:
        if r.passed is True:
            result_str = f"{C.GREEN}PASS{C.RESET}"
        elif r.passed is False:
            result_str = f"{C.RED}FAIL{C.RESET}"
        else:
            result_str = f"{C.YELLOW}N/A{C.RESET}"

        print(f"  {r.name:<14} {result_str:<16} {r.score:+.1f}     {r.cost_label}")

    print(f"  {'-' * 52}")
    print()
