"""
V2 增强终端输出

三维分、Issue 列表、基线对比表
"""

from src.core.models import DetectionReport, CheckResultV2, IssueLevel, Verdict, BackendSource


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


def print_v2_header(base_url: str, model: str, protocol: str, mode: str, degraded: bool):
    """打印 V2 检测头部"""
    degrade_warn = ""
    if degraded:
        degrade_warn = f"  {C.YELLOW}[!] 协议降级模式{C.RESET}\n"

    print(f"""
{C.BOLD}{C.CYAN}+----------------------------------------------------------+
|              [SEARCH] 中转站API检测工具                         |
|        第三方中转站 API 模型真实性与合规检测                |
+----------------------------------------------------------+{C.RESET}

  {C.DIM}Base URL:{C.RESET}  {base_url}
  {C.DIM}声称模型:{C.RESET}  {C.BOLD}{model}{C.RESET}
  {C.DIM}协议:{C.RESET}      {protocol}
  {C.DIM}模式:{C.RESET}      {mode}
{degrade_warn}""")


def _verdict_color(verdict: Verdict) -> str:
    if verdict == Verdict.PASSED_EXCELLENT:
        return C.GREEN
    elif verdict == Verdict.PASSED:
        return C.GREEN
    elif verdict == Verdict.MARGINAL:
        return C.YELLOW
    else:
        return C.RED


def _verdict_text(verdict: Verdict) -> str:
    return {
        Verdict.PASSED_EXCELLENT: "[PASS] 优秀通过",
        Verdict.PASSED: "[PASS] 通过",
        Verdict.MARGINAL: "[WARN] 勉强合格",
        Verdict.FAILED: "[FAIL] 未通过",
    }.get(verdict, "未知")


def _issue_icon(level: IssueLevel) -> str:
    return {
        IssueLevel.CRITICAL: f"{C.RED}[CRITICAL]{C.RESET}",
        IssueLevel.MAJOR: f"{C.YELLOW}[MAJOR]{C.RESET}",
        IssueLevel.MEDIUM: f"{C.YELLOW}[MEDIUM]{C.RESET}",
        IssueLevel.MINOR: f"{C.BLUE}[MINOR]{C.RESET}",
        IssueLevel.OK: f"{C.GREEN}[OK]{C.RESET}",
    }.get(level, "")


def _score_color(score: float) -> str:
    if score >= 85:
        return C.GREEN
    elif score >= 70:
        return C.GREEN
    elif score >= 50:
        return C.YELLOW
    else:
        return C.RED


def print_v2_results(report: DetectionReport):
    """打印检测结果"""
    print(f"  {C.DIM}开始检测...{C.RESET}\n")

    for i, result in enumerate(report.results, 1):
        # 状态图标
        if result.status == "pass":
            icon = f"{C.GREEN}[OK]{C.RESET}"
        elif result.status == "fail":
            icon = f"{C.RED}[FAIL]{C.RESET}"
        elif result.status == "skip":
            icon = f"{C.DIM}[SKIP]{C.RESET}"
        elif result.status == "error":
            icon = f"{C.RED}[ERROR]{C.RESET}"
        else:
            icon = f"{C.YELLOW}[?]{C.RESET}"

        score_str = f"{_score_color(result.score)}{result.score:.0f}{C.RESET}"
        cat_str = result.category.value[:4]

        print(f"  {C.DIM}[{i:2d}]{C.RESET} {icon} {C.BOLD}{result.name:<24}{C.RESET} "
              f"{C.DIM}[{cat_str}]{C.RESET} "
              f"Score: {score_str}  "
              f"{C.DIM}({result.cost_tokens} tok){C.RESET}")

        # Issues
        for issue in result.issues:
            print(f"       {_issue_icon(issue.level)} {issue.message}")

        # Details
        if result.details:
            for line in result.details.split("\n")[:3]:
                print(f"       {C.DIM}{line}{C.RESET}")

        print()


def print_v2_summary(report: DetectionReport):
    """打印汇总表"""
    print(f"  {C.BOLD}{'检测器':<26} {'类别':<6} {'分数':<8} {'状态':<8} {'Token':<8}{C.RESET}")
    print(f"  {'-' * 62}")

    for r in report.results:
        score_str = f"{_score_color(r.score)}{r.score:.0f}{C.RESET}"
        print(f"  {r.name:<24} {r.category.value[:4]:<6} {score_str:<11} {r.status:<8} {r.cost_tokens}")

    print(f"  {'-' * 62}")
    print()


def _backend_source_text(source: str) -> str:
    """后端来源的中文描述"""
    labels = {
        BackendSource.ANTHROPIC_DIRECT.value: f"{C.GREEN}Anthropic 直连{C.RESET}",
        BackendSource.BEDROCK_DIRECT.value: f"{C.GREEN}AWS Bedrock 直连{C.RESET}",
        BackendSource.KIRO_PROXY.value: f"{C.YELLOW}Kiro 代理链路 (Amazon Q){C.RESET}",
        BackendSource.VERTEX_PROXY.value: f"{C.YELLOW}Vertex AI 代理链路{C.RESET}",
        BackendSource.UNKNOWN_PROXY.value: f"{C.RED}未知代理链路{C.RESET}",
        BackendSource.UNKNOWN.value: f"{C.DIM}未识别{C.RESET}",
    }
    return labels.get(source, source)


def print_v2_verdict(report: DetectionReport):
    """打印最终裁定（v2.1 新增后端来源显示）"""
    vcolor = _verdict_color(report.verdict)
    vtext = _verdict_text(report.verdict)

    backend_label = _backend_source_text(report.backend_source)

    print(f"""{C.BOLD}{C.CYAN}+----------------------------------------------------------+
|                  [REPORT] 最终裁定                         |
+----------------------------------------------------------+{C.RESET}

  {C.BOLD}模型:{C.RESET}       {report.model}
  {C.BOLD}协议:{C.RESET}       {report.protocol.value}{' (降级)' if report.degraded else ''}
  {C.BOLD}后端来源:{C.RESET}   {backend_label}
  {C.BOLD}裁定:{C.RESET}       {vcolor}{vtext}{C.RESET}
  {C.BOLD}总分:{C.RESET}       {vcolor}{report.total_score:.1f}{C.RESET}/100

  {C.BOLD}--- 三维评分 ---{C.RESET}
  {C.BOLD}真伪分:{C.RESET}     {_score_color(report.authenticity_score)}{report.authenticity_score:.1f}{C.RESET}/100
  {C.BOLD}能力分:{C.RESET}     {_score_color(report.capability_score)}{report.capability_score:.1f}{C.RESET}/100
  {C.BOLD}合规分:{C.RESET}     {_score_color(report.compliance_score)}{report.compliance_score:.1f}{C.RESET}/100

  {C.DIM}--- 消耗统计 ---{C.RESET}
  {C.DIM}请求次数:{C.RESET}   {report.total_requests}
  {C.DIM}总 Token:{C.RESET}    {report.total_tokens}
  {C.DIM}估算费用:{C.RESET}   ~${report.estimated_cost_usd:.4f} USD
  {C.DIM}耗时:{C.RESET}        {report.duration_seconds:.1f}s
""")

    if report.has_critical:
        print(f"  {C.RED}{C.BOLD}[!] 存在 CRITICAL 级别问题，verdict 已锁定上限为 MARGINAL{C.RESET}\n")

    # 基线对比
    if report.baseline_diff:
        diff = report.baseline_diff
        print(f"  {C.BOLD}--- Baseline Diff ---{C.RESET}")
        print(f"  {C.DIM}基线分:{C.RESET}     {diff['baseline_score']:.1f}")
        print(f"  {C.DIM}当前分:{C.RESET}     {diff['current_score']:.1f}")
        delta = diff['score_delta']
        delta_color = C.GREEN if delta >= 0 else C.RED
        print(f"  {C.DIM}差异:{C.RESET}       {delta_color}{delta:+.1f}{C.RESET}")

        if diff.get("detector_diffs"):
            print(f"  {C.DIM}显著差异检测器:{C.RESET}")
            for d in diff["detector_diffs"]:
                dcolor = C.GREEN if d["delta"] >= 0 else C.RED
                print(f"    {d['name']}: {d['baseline_score']:.0f} → {d['current_score']:.0f} ({dcolor}{d['delta']:+.0f}{C.RESET})")
        print()
