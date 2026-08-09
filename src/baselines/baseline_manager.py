"""
基线管理 - 运行时采集/缓存/加载基线，差异报告

Bug 9 修复：改为运行时采集+本地缓存，不预置基线 JSON
  - --collect-baseline 用官方 API key 采集，保存到 ~/.model-detective/baselines/
  - --compare 自动查找缓存，找不到提示先采集
  - 基线只存评分和关键特征，不存原始响应
"""

import os
import json
from datetime import datetime
from pathlib import Path
from typing import Optional
from src.core.models import DetectionReport, Protocol


BASELINE_DIR = Path.home() / ".model-detective" / "baselines"


def get_baseline_path(model: str, mode: str) -> Path:
    """获取基线文件路径"""
    safe_model = model.replace("/", "_").replace(":", "_")
    return BASELINE_DIR / f"{safe_model}_{mode}.json"


def save_baseline(report: DetectionReport) -> Path:
    """保存基线到本地缓存"""
    BASELINE_DIR.mkdir(parents=True, exist_ok=True)

    baseline_data = {
        "model": report.model,
        "protocol": report.protocol.value,
        "mode": report.mode,
        "total_score": report.total_score,
        "verdict": report.verdict.value,
        "authenticity_score": report.authenticity_score,
        "capability_score": report.capability_score,
        "compliance_score": report.compliance_score,
        "detectors": [
            {
                "name": r.name,
                "category": r.category.value,
                "score": r.score,
                "weight": r.weight,
                "status": r.status,
            }
            for r in report.results if r.effective
        ],
        "collected_at": datetime.now().isoformat(),
    }

    path = get_baseline_path(report.model, report.mode)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(baseline_data, f, ensure_ascii=False, indent=2)

    return path


def load_baseline(model: str, mode: str) -> Optional[dict]:
    """加载基线"""
    path = get_baseline_path(model, mode)
    if not path.exists():
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def compare_with_baseline(report: DetectionReport) -> Optional[dict]:
    """对比当前检测与基线的差异"""
    baseline = load_baseline(report.model, report.mode)
    if not baseline:
        return None

    diff = {
        "baseline_score": baseline.get("total_score", 0),
        "current_score": report.total_score,
        "score_delta": report.total_score - baseline.get("total_score", 0),
        "baseline_verdict": baseline.get("verdict", ""),
        "current_verdict": report.verdict.value,
        "detector_diffs": [],
    }

    # 逐检测器对比
    baseline_detectors = {d["name"]: d for d in baseline.get("detectors", [])}
    for r in report.results:
        if not r.effective:
            continue
        b = baseline_detectors.get(r.name)
        if b:
            delta = r.score - b.get("score", 0)
            if abs(delta) > 5:  # 只报告差异 > 5 分的
                diff["detector_diffs"].append({
                    "name": r.name,
                    "baseline_score": b.get("score", 0),
                    "current_score": r.score,
                    "delta": delta,
                })

    return diff
