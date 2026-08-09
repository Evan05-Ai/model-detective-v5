"""
HTML 报告生成 - jinja2 模板渲染
"""

import os
from pathlib import Path
from datetime import datetime
from src.core.models import DetectionReport, Verdict, IssueLevel


TEMPLATE_DIR = Path(__file__).parent / "templates"


def generate_html_report(report: DetectionReport, output_path: str) -> str:
    """生成 HTML 报告"""
    try:
        from jinja2 import Environment, FileSystemLoader
    except ImportError:
        raise ImportError("HTML 报告需要 jinja2，请运行: pip install jinja2")

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=True,
    )
    template = env.get_template("report.html.j2")

    # 准备模板数据
    verdict_colors = {
        Verdict.PASSED_EXCELLENT: "#22c55e",
        Verdict.PASSED: "#22c55e",
        Verdict.MARGINAL: "#f59e0b",
        Verdict.FAILED: "#ef4444",
    }
    verdict_texts = {
        Verdict.PASSED_EXCELLENT: "优秀通过",
        Verdict.PASSED: "通过",
        Verdict.MARGINAL: "勉强合格",
        Verdict.FAILED: "未通过",
    }
    issue_colors = {
        IssueLevel.CRITICAL: "#ef4444",
        IssueLevel.MAJOR: "#f59e0b",
        IssueLevel.MEDIUM: "#eab308",
        IssueLevel.MINOR: "#3b82f6",
        IssueLevel.OK: "#22c55e",
    }

    html = template.render(
        report=report,
        verdict_color=verdict_colors.get(report.verdict, "#666"),
        verdict_text=verdict_texts.get(report.verdict, "未知"),
        issue_colors=issue_colors,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        results=[r for r in report.results],
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    return output_path
