#!/usr/bin/env python3
"""
中转站API检测工具 - 第三方中转站 API 模型真实性与协议合规检测工具

用法:
  # V2 默认模式（standard）
  python detect.py --url <base_url> --key <api_key> --model <model_name>

  # 快速模式
  python detect.py --url ... --key ... --model gpt-4o --mode quick

  # 完整模式 + 长上下文探针
  python detect.py --url ... --key ... --model claude-sonnet-4-5 --mode full --long-context

  # V1 兼容模式
  python detect.py --url ... --key ... --model gpt-4o --legacy

  # HTML 报告导出
  python detect.py --url ... --key ... --model gpt-4o --html report.html

  # 基线对比
  python detect.py --url ... --key ... --model gpt-4o --compare
"""

import argparse
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.core.models import Protocol, RunMode
from src.core.protocol_resolver import ProtocolResolver
from src.core.runner import Runner
from src.core.modes import estimate_long_context_cost
from src.protocols.openai.client import OpenAIClient
from src.protocols.anthropic.client import AnthropicClient
from src.protocols.gemini.client import GeminiClient
from src.protocols.openai.detectors import build_active_detectors as openai_active, build_passive_detectors as openai_passive
from src.protocols.anthropic.detectors import build_active_detectors as anthropic_active, build_passive_detectors as anthropic_passive
from src.protocols.gemini.detectors import build_active_detectors as gemini_active, build_passive_detectors as gemini_passive
from src.baselines.baseline_manager import save_baseline, compare_with_baseline
from src.reports.terminal import print_v2_header, print_v2_results, print_v2_summary, print_v2_verdict, C
from src.reports.html_report import generate_html_report


def run_v2_detection(base_url: str, api_key: str, model: str,
                     mode: RunMode, protocol: str, long_context: bool,
                     collect_baseline: bool, compare: bool, html_path: str = None):
    """执行 V2 检测流程"""

    # v2.3: 启动时校验三协议检测器配置
    from src.protocols.openai.config import validate_weights as validate_openai
    from src.protocols.anthropic.config import validate_weights as validate_anthropic
    from src.protocols.gemini.config import validate_weights as validate_gemini
    try:
        validate_openai()
        validate_anthropic()
        validate_gemini()
    except RuntimeError as e:
        print(f"  {C.RED}[FAIL] Detector config validation failed:{C.RESET}\n{e}")
        sys.exit(1)

    # 1. 协议解析 + 降级回退
    resolver = ProtocolResolver(base_url, api_key, model)

    if protocol == "auto":
        resolved_protocol, degraded, degrade_reason = resolver.resolve()
    else:
        resolved_protocol = Protocol(protocol)
        degraded = False
        degrade_reason = ""

    # 2. 创建协议客户端
    if resolved_protocol == Protocol.OPENAI:
        client = OpenAIClient(base_url, api_key, model)
        active_dets = openai_active(long_context=long_context)
        passive_dets = openai_passive()
    elif resolved_protocol == Protocol.ANTHROPIC:
        client = AnthropicClient(base_url, api_key, model)
        active_dets = anthropic_active(long_context=long_context)
        passive_dets = anthropic_passive()
    elif resolved_protocol == Protocol.GEMINI:
        client = GeminiClient(base_url, api_key, model)
        active_dets = gemini_active(long_context=long_context)
        passive_dets = gemini_passive()
    else:
        print(f"错误: 不支持的协议 {resolved_protocol}")
        sys.exit(1)

    # 3. 打印头部
    print_v2_header(base_url, model, resolved_protocol.value, mode.value, degraded)
    if degrade_reason:
        print(f"  {C.YELLOW}[!] {degrade_reason}{C.RESET}\n")

    # 4. 执行检测
    runner = Runner(
        client=client,
        active_detectors=active_dets,
        passive_detectors=passive_dets,
        protocol=resolved_protocol,
        model=model,
        mode=mode,
        degraded=degraded,
    )

    report = runner.run()

    # 5. 基线对比
    if compare:
        diff = compare_with_baseline(report)
        if diff:
            report.baseline_diff = diff
        else:
            print(f"\n  {C.YELLOW}[!] No baseline found, please run --collect-baseline first{C.RESET}\n")

    # 6. 采集基线
    if collect_baseline:
        path = save_baseline(report)
        print(f"\n  {C.GREEN}[OK] Baseline saved to: {path}{C.RESET}\n")

    # 7. 打印结果
    print_v2_results(report)
    print_v2_summary(report)
    print_v2_verdict(report)

    # 8. HTML 报告
    if html_path:
        try:
            generate_html_report(report, html_path)
            print(f"\n  {C.GREEN}[OK] HTML report generated: {html_path}{C.RESET}\n")
        except ImportError as e:
            print(f"\n  {C.RED}[FAIL] HTML report generation failed: {e}{C.RESET}\n")

    return report


def run_v1_detection(base_url: str, api_key: str, model: str, light: bool):
    """执行 V1 检测流程（兼容模式）"""
    from src.api_client import APIClient
    from src.checks import V1_CHECKS
    from src.reporter import print_header, print_check_result, print_verdict, print_summary_table

    client = APIClient(base_url, api_key, model)
    print_header(base_url, model, api_key)

    checks = V1_CHECKS[:4] if light else V1_CHECKS
    if light:
        print(f"  {C.CYAN}[LIGHT] Lightweight mode: skipping deep checks{C.RESET}\n")

    results = []
    print(f"  {C.DIM}开始检测...{C.RESET}\n")

    for i, (name, check_fn, cost_label) in enumerate(checks, 1):
        print(f"  {C.DIM}▶ 执行: {name} ({cost_label}){C.RESET}", end="\r")
        print(f"  {'':50}", end="\r")
        result = check_fn(client)
        results.append(result)
        print_check_result(result, i)

    print_summary_table(results)

    total_score = 0
    total_confidence = 0
    valid_results = [r for r in results if r.confidence > 0]

    if valid_results:
        total_weight = sum(r.confidence for r in valid_results)
        total_score = sum(r.score * r.confidence for r in valid_results) / total_weight
        total_confidence = total_weight / len(valid_results)

    cost = client.get_cost_summary()
    print_verdict(total_score, total_confidence, cost["total_tokens"], cost["total_requests"], model)

    return total_score


def load_config(config_path: str, provider: str) -> tuple:
    """从配置文件加载 provider 信息"""
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    if provider not in config.get("providers", {}):
        available = list(config.get("providers", {}).keys())
        print(f"错误: provider '{provider}' 不存在")
        print(f"可用 provider: {available}")
        sys.exit(1)

    p = config["providers"][provider]
    return p["base_url"], p["api_key"]


def main():
    parser = argparse.ArgumentParser(
        description="中转站API检测工具 - 第三方中转站 API 模型真实性与协议合规检测",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # V2 标准检测
  python detect.py --url https://api.example.com/v1 --key sk-xxx --model gpt-4o

  # 快速模式
  python detect.py --url ... --key ... --model gpt-4o --mode quick

  # 完整模式 + 长上下文
  python detect.py --url ... --key ... --model claude-sonnet-4-5 --mode full --long-context

  # V1 兼容模式
  python detect.py --url ... --key ... --model gpt-4o --legacy

  # HTML 报告
  python detect.py --url ... --key ... --model gpt-4o --html report.html

  # 基线采集/对比
  python detect.py --url ... --key ... --model gpt-4o --collect-baseline
  python detect.py --url ... --key ... --model gpt-4o --compare
        """
    )

    parser.add_argument("--url", help="API Base URL")
    parser.add_argument("--key", help="API Key")
    parser.add_argument("--model", required=True, help="声称的模型名称")
    parser.add_argument("--config", help="配置文件路径 (JSON)")
    parser.add_argument("--provider", help="配置文件中的 provider 名称")

    # V2 参数
    parser.add_argument("--mode", choices=["quick", "standard", "full"], default="standard",
                        help="运行模式: quick(~6请求)/standard(~12请求)/full(~13+请求)")
    parser.add_argument("--protocol", choices=["auto", "openai", "anthropic", "gemini"], default="auto",
                        help="指定协议（默认自动检测）")
    parser.add_argument("--long-context", action="store_true",
                        help="启用长上下文探针（32k→100k→200k，消耗大量 token）")
    parser.add_argument("--html", metavar="PATH", help="导出 HTML 报告到指定路径")
    parser.add_argument("--collect-baseline", action="store_true", help="采集基线数据到本地缓存")
    parser.add_argument("--compare", action="store_true", help="与已采集的基线对比")
    parser.add_argument("--yes", action="store_true", help="跳过确认提示")

    # V1 兼容参数
    parser.add_argument("--legacy", action="store_true", help="使用 V1 检测模式（6项基础检测）")
    parser.add_argument("--light", action="store_true", help="轻量模式（V1: 前4项检测 / V2: 等同 --mode quick）")

    args = parser.parse_args()

    # 获取连接信息
    if args.config and args.provider:
        base_url, api_key = load_config(args.config, args.provider)
    elif args.url and args.key:
        base_url = args.url
        api_key = args.key
    else:
        print("错误: 请提供 --url + --key，或 --config + --provider")
        parser.print_help()
        sys.exit(1)

    # V1 兼容模式
    if args.legacy:
        score = run_v1_detection(base_url, api_key, args.model, args.light)
        if score < -0.3:
            sys.exit(1)
        elif score < 0:
            sys.exit(2)
        else:
            sys.exit(0)

    # V2 模式
    mode = RunMode(args.mode)

    # --light 在 V2 下等价 quick
    if args.light and mode != RunMode.QUICK:
        mode = RunMode.QUICK
        print(f"  {C.CYAN}[INFO] --light in V2 is equivalent to --mode quick{C.RESET}\n")

    # 长上下文确认
    if args.long_context:
        estimated_cost = estimate_long_context_cost()
        print(f"  {C.YELLOW}[WARN] Long context probe will consume ~332k tokens, estimated cost ${estimated_cost:.2f} USD{C.RESET}")
        if not args.yes:
            try:
                response = input(f"  确认执行？(y/N): ")
                if response.lower() != "y":
                    print("  已取消长上下文探针")
                    args.long_context = False
            except EOFError:
                print(f"  {C.YELLOW}[WARN] Non-interactive environment, skipping automatically. Use --yes to confirm.{C.RESET}")
                args.long_context = False

    # 执行 V2 检测
    report = run_v2_detection(
        base_url=base_url,
        api_key=api_key,
        model=args.model,
        mode=mode,
        protocol=args.protocol,
        long_context=args.long_context,
        collect_baseline=args.collect_baseline,
        compare=args.compare,
        html_path=args.html,
    )

    # 退出码
    sys.exit(report.exit_code)


if __name__ == "__main__":
    main()
