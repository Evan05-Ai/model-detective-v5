"""
Evaluation Reporter - 测评报告生成器

支持生成：
- JSON 格式报告（用于 API 返回）
- HTML 格式报告（用于前端展示）
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from .eval_engine import EvalResult


# ==================== 颜色映射 ====================

VERDICT_COLORS = {
    "excellent": "#22c55e",
    "good": "#3b82f6",
    "average": "#f59e0b",
    "poor": "#ef4444",
}

VERDICT_LABELS = {
    "excellent": "优秀",
    "good": "良好",
    "average": "一般",
    "poor": "较差",
}

DIMENSION_LABELS = {
    "basic_language": "基础语言",
    "technical": "技术能力",
    "advanced_cognition": "高级认知",
    "practical": "实用能力",
    "boundary": "边界鲁棒",
}


def result_to_dict(result: EvalResult) -> dict:
    """将 EvalResult 转换为 JSON 可序列化的 dict"""
    return {
        "model": result.model,
        "protocol": result.protocol,
        "total_score": round(result.total_score, 1),
        "verdict": result.verdict,
        "verdict_cn": VERDICT_LABELS.get(result.verdict, "未知"),
        "dimension_scores": {
            k: round(v, 1) for k, v in result.dimension_scores.items()
        },
        "question_results": result.question_results,
        "duration_seconds": round(result.duration_seconds, 1),
        "total_tokens": result.total_tokens,
        "estimated_cost_usd": round(result.estimated_cost_usd, 6),
        "errors": result.errors,
    }


def results_to_comparison(results: list[EvalResult]) -> dict:
    """生成多模型对比数据"""
    comparison = {
        "models": [],
        "ranking": [],
        "generated_at": datetime.now().isoformat(),
    }

    # 按总分排序
    sorted_results = sorted(results, key=lambda r: r.total_score, reverse=True)

    for i, result in enumerate(sorted_results):
        rd = result_to_dict(result)
        rd["rank"] = i + 1
        comparison["models"].append(rd)

    comparison["ranking"] = [
        {"rank": i + 1, "model": r.model, "score": round(r.total_score, 1)}
        for i, r in enumerate(sorted_results)
    ]

    return comparison


def generate_html_report(results: list[EvalResult]) -> str:
    """生成 HTML 格式的测评报告"""
    comparison = results_to_comparison(results)

    rows_html = ""
    for m in comparison["models"]:
        score = m["total_score"]
        color = VERDICT_COLORS.get(m["verdict"], "#666")
        verdict_cn = m["verdict_cn"]
        dims_html = ""
        for dim_key, dim_val in m.get("dimension_scores", {}).items():
            dim_label = DIMENSION_LABELS.get(dim_key, dim_key)
            dim_color = color if dim_val >= 70 else ("#f59e0b" if dim_val >= 50 else "#ef4444")
            dims_html += f'<div class="dim"><span class="dim-label">{dim_label}</span><span class="dim-score" style="color:{dim_color}">{dim_val}</span></div>'

        rows_html += f'''
        <tr>
            <td><strong>{m["model"]}</strong></td>
            <td>{m["protocol"]}</td>
            <td><span class="score" style="color:{color}">{score}</span></td>
            <td><span class="verdict" style="background:{color}22;color:{color}">{verdict_cn}</span></td>
            <td>{m["duration_seconds"]}s</td>
            <td>{m["total_tokens"]}</td>
            <td>${m["estimated_cost_usd"]:.6f}</td>
        </tr>
        <tr><td colspan="7" class="dims">{dims_html}</td></tr>
        '''

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Model Detective - 模型能力测评报告</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: 'Inter', -apple-system, sans-serif; background: #060810; color: #f0f4fc; padding: 2rem; }}
h1 {{ text-align: center; margin-bottom: 2rem; background: linear-gradient(135deg, #4a9eff, #22d3ee); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-size: 2rem; }}
table {{ width: 100%; border-collapse: collapse; background: #0e1320; border-radius: 12px; overflow: hidden; }}
th {{ background: #161d2e; padding: 12px 16px; text-align: left; font-size: 0.85rem; color: #a8b5c8; text-transform: uppercase; letter-spacing: 0.05em; }}
td {{ padding: 12px 16px; border-bottom: 1px solid rgba(255,255,255,0.06); font-size: 0.92rem; }}
tr:hover {{ background: rgba(74,158,255,0.04); }}
.score {{ font-weight: 700; font-family: 'JetBrains Mono', monospace; font-size: 1.1rem; }}
.verdict {{ padding: 2px 10px; border-radius: 100px; font-size: 0.8rem; font-weight: 600; }}
.dims {{ padding: 12px 16px !important; }}
.dim {{ display: inline-block; margin-right: 1.5rem; margin-bottom: 0.5rem; }}
.dim-label {{ font-size: 0.8rem; color: #6a7689; margin-right: 0.3rem; }}
.dim-score {{ font-weight: 700; font-family: 'JetBrains Mono', monospace; }}
.footer {{ text-align: center; margin-top: 2rem; color: #6a7689; font-size: 0.85rem; }}
</style>
</head>
<body>
<h1>🔍 Model Detective — 模型能力测评报告</h1>
<table>
<thead>
<tr>
    <th>排名</th>
    <th>模型</th>
    <th>协议</th>
    <th>总分</th>
    <th>评定</th>
    <th>耗时</th>
    <th>Tokens</th>
    <th>费用</th>
</tr>
</thead>
<tbody>
{rows_html}
</tbody>
</table>
<div class="footer">
    生成时间: {comparison["generated_at"]} · Model Detective v2.6
</div>
</body>
</html>'''

    return html
