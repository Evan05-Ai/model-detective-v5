"""
Model Detective Web - Flask backend

API endpoints:
  GET  /                     -> HTML page
  POST /api/probe            -> Probe relay's /v1/models
  POST /api/detect           -> Submit detection job(s)
  GET  /api/status/<job_id>  -> Poll job status (SSE + JSON)
  GET  /api/report/<job_id>  -> Full report JSON
  POST /api/evaluate         -> Submit evaluation job(s)
  GET  /api/evaluate/status/<job_id> -> Poll evaluation status
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import secrets
from dataclasses import dataclass, field
from typing import Any, Optional

# ── path setup ──────────────────────────────────────────────
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

from flask import Flask, request, jsonify, Response, render_template, stream_with_context

# ── Flask app ───────────────────────────────────────────────
app = Flask(__name__, template_folder="templates", static_folder="static")
app.jinja_env.auto_reload = True
app.config['TEMPLATES_AUTO_RELOAD'] = True

# ── Job store (thread-safe) ─────────────────────────────────
_LOCK = threading.Lock()

@dataclass
class Job:
    id: str
    status: str = "queued"          # queued / running / done / error
    base_url: str = ""
    api_key_masked: str = ""
    models: list[str] = field(default_factory=list)
    mode: str = "standard"
    protocol: str = "auto"
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    progress: list[dict] = field(default_factory=list)   # per-model progress events
    reports: list[dict] = field(default_factory=list)     # completed report dicts
    error: Optional[str] = None

_JOBS: dict[str, Job] = {}
_MAX_JOBS = 200          # prevent unbounded memory growth
_MAX_CONCURRENT = 4       # limit concurrent detection threads
_JOB_SEMA = threading.Semaphore(_MAX_CONCURRENT)

def _new_job_id() -> str:
    return secrets.token_urlsafe(8)

def _gc_jobs():
    """Remove old completed/errored jobs to prevent unbounded memory growth."""
    if len(_JOBS) <= _MAX_JOBS:
        return
    # Sort by finished_at (or created_at), drop oldest completed ones
    candidates = []
    for jid, j in _JOBS.items():
        ts = j.finished_at or j.created_at
        candidates.append((ts, jid, j.status))
    candidates.sort()
    for _, jid, status in candidates:
        if status in ("done", "error"):
            del _JOBS[jid]
            if len(_JOBS) <= _MAX_JOBS:
                break

def _mask_key(key: str) -> str:
    if len(key) <= 8:
        return "*" * len(key)
    return key[:4] + "*" * (len(key) - 6) + key[-2:]

# ── Model classification (inspired by veridrop probe.py) ─────

def _classify_model(model_id: str) -> str:
    """Map a model id to a protocol bucket."""
    s = model_id.strip().lower().removeprefix("models/")
    if s.startswith("claude") or "/claude" in s:
        return "anthropic"
    if s.startswith("gemini") or "/gemini" in s:
        return "gemini"
    if s.startswith(("gpt-", "o1", "o3", "o4", "chatgpt", "text-embedding-")):
        return "openai"
    if s.startswith(("openai/", "azure/openai")):
        return "openai"
    # default: openai-compatible
    return "openai"

def _model_probe_urls(base_url: str) -> list[str]:
    """Generate candidate /models URLs.

    Tries OpenAI-compatible patterns first, then Gemini-native patterns.
    Inspired by veridrop's multi-URL fallback approach.
    """
    base = base_url.rstrip("/")
    candidates = []
    # If base already ends with /v1 or /v1beta, try /models directly first
    if base.endswith("/v1"):
        candidates.append(f"{base}/models")
    if base.endswith("/v1beta"):
        candidates.append(f"{base}/models")
    # Common OpenAI-compatible patterns
    for suffix in ["/v1/models", "/models", "/api/v1/models", "/openai/v1/models"]:
        full = f"{base}{suffix}"
        if full not in candidates:
            candidates.append(full)
    return candidates


# ── SSRF Protection (v2.8) ────────────────────────────────────
# 禁止访问内网地址，防止 SSRF 攻击
_FORBIDDEN_URL_PATTERNS = [
    "http://127.",
    "http://10.",
    "http://192.168.",
    "http://169.254.",
    "http://0.",
    "http://localhost",
    "http://[::1]",
    "https://127.",
    "https://10.",
    "https://192.168.",
    "https://169.254.",
    "https://0.",
    "https://localhost",
    "https://[::1]",
]


def _validate_base_url_no_ssrf(base_url: str) -> tuple[bool, str]:
    """验证 base_url 不会导致 SSRF 攻击
    
    Returns:
        (is_valid, error_message)
    """
    url_lower = base_url.lower()
    
    # 检查是否包含禁止的内网地址
    for forbidden in _FORBIDDEN_URL_PATTERNS:
        if url_lower.startswith(forbidden):
            return False, f"禁止访问内网地址: {base_url}"
    
    # 检查是否包含 localhost
    if "localhost" in url_lower:
        return False, "禁止访问 localhost"
    
    return True, ""


# ── Probe endpoint ──────────────────────────────────────────

import requests as _requests

@app.post("/api/probe")
def api_probe():
    """Probe a relay's models endpoint."""
    data = request.get_json(force=True, silent=True) or {}
    base_url = (data.get("base_url") or "").strip()
    api_key = (data.get("api_key") or "").strip()

    if not base_url:
        return jsonify({"ok": False, "error": "base_url is required"}), 400
    if not base_url.startswith(("http://", "https://")):
        return jsonify({"ok": False, "error": "base_url must start with http(s)://"}), 400
    # v2.8: SSRF 防护
    is_valid, err = _validate_base_url_no_ssrf(base_url)
    if not is_valid:
        return jsonify({"ok": False, "error": err}), 400
    if not api_key or len(api_key) < 8:
        return jsonify({"ok": False, "error": "api_key looks invalid"}), 200

    urls = _model_probe_urls(base_url)
    from src.core.http_utils import BROWSER_HEADERS
    headers_bearer = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        **BROWSER_HEADERS,
    }
    headers_anthropic = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
        **BROWSER_HEADERS,
    }

    # Single-pass scan: try each URL with both auth strategies
    # Track auth failures so we don't need a second round-trip
    auth_failure_count = 0
    total_attempts = 0

    for url in urls:
        for headers in [headers_bearer, headers_anthropic]:
            total_attempts += 1
            try:
                resp = _requests.get(url, headers=headers, timeout=8)
            except _requests.exceptions.Timeout:
                continue
            except _requests.exceptions.ConnectionError:
                continue
            except Exception:
                continue

            if resp.status_code == 404:
                continue
            if resp.status_code in (401, 403):
                auth_failure_count += 1
                continue
            if resp.status_code >= 400:
                continue

            try:
                payload = resp.json()
            except Exception:
                continue

            ids = _extract_model_ids(payload)
            by_proto: dict[str, list[str]] = {"anthropic": [], "openai": [], "gemini": []}
            for mid in ids:
                bucket = _classify_model(mid)
                if bucket and mid not in by_proto[bucket]:
                    by_proto[bucket].append(mid)

            for p in by_proto:
                by_proto[p] = _sort_by_preference(p, by_proto[p])

            # 推断有效的 base_url（用于前端后续请求）
            # 根据成功探测的 URL 推断 base_url 应该包含什么路径
            effective_base_url = base_url.rstrip("/")
            if "/v1/models" in url and not effective_base_url.endswith("/v1"):
                # 探测的是 /v1/models，说明 API 使用 /v1 前缀
                effective_base_url = effective_base_url + "/v1"
            elif "/api/v1/models" in url and not effective_base_url.endswith("/api/v1"):
                # 探测的是 /api/v1/models
                effective_base_url = effective_base_url + "/api/v1"
            elif "/openai/v1/models" in url and not effective_base_url.endswith("/openai/v1"):
                # 探测的是 /openai/v1/models
                effective_base_url = effective_base_url + "/openai/v1"
            # 如果探测的是 /models（不带 /v1），保持 base_url 不变

            return jsonify({
                "ok": True,
                "auth_ok": True,
                "models_endpoint_supported": True,
                "raw_count": len(ids),
                "all_models": ids,
                "by_protocol": by_proto,
                "status": resp.status_code,
                "effective_base_url": effective_base_url,
            })

    # If every attempt returned 401/403, it's an auth failure
    if auth_failure_count > 0 and auth_failure_count == total_attempts:
        return jsonify({
            "ok": False, "auth_ok": False,
            "error": "Authentication failed - check your API key",
        }), 200

    # All URLs failed - models endpoint not available
    return jsonify({
        "ok": True,
        "auth_ok": True,
        "models_endpoint_supported": False,
        "raw_count": 0,
        "all_models": [],
        "by_protocol": {"anthropic": [], "openai": [], "gemini": []},
        "error": "Could not reach /v1/models endpoint. You can still type model names manually.",
    }), 200

def _extract_model_ids(payload: Any) -> list[str]:
    """Extract model IDs from various response shapes."""
    ids = []
    if isinstance(payload, dict):
        data_list = payload.get("data") or payload.get("models") or []
        if isinstance(data_list, list):
            for item in data_list:
                if isinstance(item, dict):
                    mid = item.get("id") or item.get("name") or ""
                    if mid:
                        ids.append(mid)
                elif isinstance(item, str):
                    ids.append(item)
        # Anthropic-style response
        if not ids and "id" in payload:
            ids.append(payload["id"])
    elif isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                mid = item.get("id") or item.get("name") or ""
                if mid:
                    ids.append(mid)
            elif isinstance(item, str):
                ids.append(item)
    return ids

# ── Model preference sorting ────────────────────────────────

_PREF_ORDER = {
    "anthropic": [
        "claude-opus-4", "claude-sonnet-4", "claude-haiku-4",
        "claude-3-5-sonnet", "claude-3-5-haiku", "claude-3-opus",
        "claude-3-sonnet", "claude-3-haiku",
    ],
    "openai": [
        "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4", "gpt-3.5-turbo",
        "o1", "o3", "o4-mini",
    ],
    "gemini": [
        "gemini-2", "gemini-1.5-pro", "gemini-1.5-flash",
        "gemini-pro", "gemini-flash",
    ],
}

def _sort_by_preference(protocol: str, models: list[str]) -> list[str]:
    prefs = _PREF_ORDER.get(protocol, [])
    def key_fn(m):
        ml = m.lower()
        for i, p in enumerate(prefs):
            if p in ml:
                return (0, i, ml)
        return (1, 0, ml)
    return sorted(models, key=key_fn)

# ── Detection endpoint ───────────────────────────────────────

@app.post("/api/detect")
def api_detect():
    """Submit a detection job for one or more models."""
    data = request.get_json(force=True, silent=True) or {}
    base_url = (data.get("base_url") or "").strip()
    api_key = (data.get("api_key") or "").strip()
    models = data.get("models") or []
    mode = (data.get("mode") or "standard").strip().lower()
    protocol = (data.get("protocol") or "auto").strip().lower()


    # validation
    if not base_url.startswith(("http://", "https://")):
        return jsonify({"ok": False, "error": "base_url must start with http(s)://"}), 400
    # v2.8: SSRF 防护
    is_valid, err = _validate_base_url_no_ssrf(base_url)
    if not is_valid:
        return jsonify({"ok": False, "error": err}), 400
    if not api_key or len(api_key) < 8:
        return jsonify({"ok": False, "error": "api_key looks invalid"}), 400
    if not models or not isinstance(models, list):
        return jsonify({"ok": False, "error": "Please select at least one model"}), 400
    # Validate individual model names
    clean_models = []
    for m in models:
        if not isinstance(m, str) or not m.strip():
            return jsonify({"ok": False, "error": f"Invalid model name: {m!r}"}), 400
        if len(m) > 200:
            return jsonify({"ok": False, "error": f"Model name too long (max 200 chars): {m[:50]}..."}), 400
        clean_models.append(m.strip())
    models = clean_models
    if mode not in ("quick", "standard", "full"):
        return jsonify({"ok": False, "error": "mode must be quick/standard/full"}), 400

    job_id = _new_job_id()
    job = Job(
        id=job_id,
        base_url=base_url,
        api_key_masked=_mask_key(api_key),
        models=list(models),
        mode=mode,
        protocol=protocol,
    )
    with _LOCK:
        _gc_jobs()
        _JOBS[job_id] = job

    # start background execution (semaphore limits concurrency)
    t = threading.Thread(target=_run_detection, args=(job_id, base_url, api_key, models, mode, protocol), daemon=True)
    t.start()

    return jsonify({"ok": True, "job_id": job_id})

# ── SSE status endpoint ──────────────────────────────────────

@app.get("/api/status/<job_id>")
def api_status(job_id: str):
    """Poll job status. If Accept header is text/event-stream, use SSE."""
    with _LOCK:
        job = _JOBS.get(job_id)
    if job is None:
        return jsonify({"ok": False, "error": "Job not found"}), 404

    accept = request.headers.get("Accept", "")
    if "text/event-stream" in accept:
        return Response(
            stream_with_context(_sse_stream(job_id)),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # JSON poll
    return jsonify(_job_to_dict(job))

def _sse_stream(job_id: str):
    """Server-Sent Events stream for real-time progress.

    All job field reads happen under _LOCK to prevent torn reads
    while _run_detection is concurrently mutating the job.
    """
    last_idx = 0
    while True:
        with _LOCK:
            job = _JOBS.get(job_id)
            if job is None:
                break
            new_events = list(job.progress[last_idx:])
            last_idx = len(job.progress)
            is_done = job.status in ("done", "error")
            if is_done:
                final = _job_to_dict(job)

        if job is None:
            yield f"event: error\ndata: {json.dumps({'error': 'Job not found'})}\n\n"
            return

        for evt in new_events:
            yield f"event: progress\ndata: {json.dumps(evt, ensure_ascii=False)}\n\n"

        if is_done:
            yield f"event: complete\ndata: {json.dumps(final, ensure_ascii=False)}\n\n"
            return

        time.sleep(0.5)

def _job_to_dict(job: Job) -> dict:
    return {
        "ok": True,
        "job_id": job.id,
        "status": job.status,
        "models": job.models,
        "mode": job.mode,
        "base_url": job.base_url,
        "api_key_masked": job.api_key_masked,
        "progress": job.progress,
        "reports": job.reports,
        "error": job.error,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
    }

# ── Report endpoint ──────────────────────────────────────────

@app.get("/api/report/<job_id>")
def api_report(job_id: str):
    with _LOCK:
        job = _JOBS.get(job_id)
    if job is None:
        return jsonify({"ok": False, "error": "Job not found"}), 404
    return jsonify(_job_to_dict(job))

# ── Background detection runner ──────────────────────────────

def _run_detection(job_id: str, base_url: str, api_key: str, models: list[str], mode: str, protocol: str):
    """Run detection for each model sequentially (semaphore-gated)."""
    _JOB_SEMA.acquire()
    try:
        with _LOCK:
            job = _JOBS.get(job_id)
            if job is None:
                return
            job.status = "running"
            job.started_at = time.time()

        total = len(models)
        for idx, model_name in enumerate(models):
            _push_progress(job_id, {
                "type": "model_start",
                "model": model_name,
                "index": idx,
                "total": total,
            })

            try:
                report_dict = _execute_single_detection(base_url, api_key, model_name, mode, protocol)
                _push_progress(job_id, {
                    "type": "model_done",
                    "model": model_name,
                    "index": idx,
                    "total": total,
                    "report": report_dict,
                })
                with _LOCK:
                    j = _JOBS.get(job_id)
                    if j:
                        j.reports.append(report_dict)
            except Exception as e:
                _push_progress(job_id, {
                    "type": "model_error",
                    "model": model_name,
                    "index": idx,
                    "total": total,
                    "error": str(e),
                })

        with _LOCK:
            j = _JOBS.get(job_id)
            if j:
                j.status = "done"
                j.finished_at = time.time()

        _push_progress(job_id, {
            "type": "all_done",
            "total": total,
        })
    finally:
        _JOB_SEMA.release()

def _push_progress(job_id: str, event: dict):
    with _LOCK:
        j = _JOBS.get(job_id)
        if j:
            j.progress.append(event)

def _execute_single_detection(base_url: str, api_key: str, model: str, mode: str, protocol: str) -> dict:
    """Execute a single model detection and return a serializable report dict."""
    from src.core.models import Protocol, RunMode
    from src.core.protocol_resolver import ProtocolResolver
    from src.core.runner import Runner
    from src.protocols.openai.client import OpenAIClient
    from src.protocols.anthropic.client import AnthropicClient
    from src.protocols.gemini.client import GeminiClient
    from src.protocols.openai.detectors import build_active_detectors as openai_active, build_passive_detectors as openai_passive
    from src.protocols.anthropic.detectors import build_active_detectors as anthropic_active, build_passive_detectors as anthropic_passive
    from src.protocols.gemini.detectors import build_active_detectors as gemini_active, build_passive_detectors as gemini_passive

    # protocol resolve
    if protocol == "auto":
        resolver = ProtocolResolver(base_url, api_key, model)
        resolved_protocol, degraded, degrade_reason = resolver.resolve()
        # v2.4: 使用 resolver 修正后的 base_url（可能已补 /v1）
        effective_base_url = resolver.base_url
    else:
        resolved_protocol = Protocol(protocol)
        degraded = False
        degrade_reason = ""
        effective_base_url = base_url

    # create client + detectors
    if resolved_protocol == Protocol.OPENAI:
        client = OpenAIClient(effective_base_url, api_key, model)
        active_dets = openai_active()
        passive_dets = openai_passive()
    elif resolved_protocol == Protocol.ANTHROPIC:
        client = AnthropicClient(effective_base_url, api_key, model)
        active_dets = anthropic_active()
        passive_dets = anthropic_passive()
    elif resolved_protocol == Protocol.GEMINI:
        client = GeminiClient(effective_base_url, api_key, model)
        active_dets = gemini_active()
        passive_dets = gemini_passive()
    else:
        raise ValueError(f"Unsupported protocol: {resolved_protocol}")

    run_mode = RunMode(mode)

    runner = Runner(
        client=client,
        active_detectors=active_dets,
        passive_detectors=passive_dets,
        protocol=resolved_protocol,
        model=model,
        mode=run_mode,
        degraded=degraded,
    )

    report = runner.run()


    # serialize report
    return _serialize_report(report, resolved_protocol, degraded, degrade_reason, effective_base_url)

# ── 检测器中文名称 + 通俗解释映射 ──────────────────────────
DETECTOR_META = {
    # Anthropic
    "thinking_signature": {
        "cn_name": "思维签名验证",
        "cn_desc": "验证 Claude 独有的加密思维签名。真实 Claude 的思维块会附带加密签名，中转站通常无法伪造或完整传递此签名。这是判断模型真伪最核心的检测项。",
    },
    "identity": {
        "cn_name": "身份认知检测",
        "cn_desc": "直接询问模型的身份。真实的 Claude 会自报为 Claude/Anthropic，如果自报为其他身份（如 Kiro、GPT），说明请求经过了转发或模型被替换。",
    },
    "consistency": {
        "cn_name": "响应稳定性检测",
        "cn_desc": "在温度=0时重复发送相同请求，验证模型是否给出稳定一致的回答。真实模型应在相同条件下输出高度一致的结果。",
    },
    "behavioral_signature": {
        "cn_name": "行为指纹检测",
        "cn_desc": "分析模型的回答风格和排版习惯。Claude 有独特的行为特征：倾向使用 Markdown 编号列表、加粗文本、以及特定的礼貌措辞。如果回答风格与 Claude 差异较大，可能不是真实模型。",
    },
    "knowledge": {
        "cn_name": "知识截止检测",
        "cn_desc": "通过询问 2024 年美国大选等近期事件，判断模型的知识截止日期。较新的模型应当知道这些事件，如果不知道，可能是旧模型冒充新模型。",
    },
    # OpenAI
    "basic_request": {
        "cn_name": "基础请求检测",
        "cn_desc": "发送最简单的请求，验证模型是否能正常响应，以及响应中的 model 字段是否与声称的一致。",
    },
    "model_consistency": {
        "cn_name": "模型一致性检测",
        "cn_desc": "多次请求验证 model 字段是否一致，并检查是否返回假模型名或开源模型名。",
    },
    "long_context": {
        "cn_name": "长上下文检测",
        "cn_desc": "在海量文本中藏入一个密码，验证模型是否能找到。测试模型是否真正支持大上下文窗口。",
    },
    # Gemini
    "model_info": {
        "cn_name": "模型信息检测",
        "cn_desc": "查询 Gemini 模型列表并验证 modelVersion 字段是否与声称一致。",
    },
    # 通用
    "protocol": {
        "cn_name": "协议合规检测",
        "cn_desc": "验证 API 响应结构是否符合官方协议规范。包括必需字段、字段类型、响应格式等。合规的 API 应当返回完整的结构化数据。",
    },
    "integrity": {
        "cn_name": "一致性检测",
        "cn_desc": "被动观察所有检测器的请求结果，检查不同请求返回的模型名称是否一致。如果中转站在不同请求中返回了不同的模型名称，说明后端可能使用了多个模型或进行了模型替换。",
    },
    "billing_integrity": {
        "cn_name": "计费完整性审计",
        "cn_desc": "使用精确的 Token 计数工具对比中转站上报的 Token 数。检测是否存在虚报 Token 数量、伪造缓存计费字段、或计费倍率过高等问题。这是检测中转站计费诚信的核心项目。",
    },
    "function_calling": {
        "cn_name": "函数调用检测",
        "cn_desc": "向模型提供工具定义，验证模型是否能正确发起函数调用。真实的 Claude/GPT/Gemini 都支持函数调用，且返回的工具调用 ID 有特定的前缀格式（如 toolu_）。",
    },
    "message_id": {
        "cn_name": "消息ID规范检测",
        "cn_desc": "验证响应中的消息 ID 是否符合 Claude 的命名规范（msg_ 前缀）。原生 Anthropic API 生成的 ID 有固定前缀格式，不符合规范可能意味着非原生链路。",
    },
    "token_usage": {
        "cn_name": "Token计费验证",
        "cn_desc": "验证 usage 字段中的 Token 计数是否合理。检查 input/output Token 是否为 0（虚报）、是否与估算严重不符、以及 total = prompt + completion 是否成立。",
    },
    "token_billing": {
        "cn_name": "Token计费验证",
        "cn_desc": "验证 usage 字段中的 Token 计数是否合理，以及流式与非流式 Token 是否一致。",
    },
    "structured_output": {
        "cn_name": "结构化输出检测",
        "cn_desc": "要求模型输出特定格式的结构化数据（如 JSON），验证模型是否支持结构化输出能力。",
    },
    "pdf": {
        "cn_name": "PDF能力检测",
        "cn_desc": "发送包含特定密码的 PDF 文件，验证模型是否能从 PDF 中提取信息。这是 Claude 独有的能力。",
    },
}

CATEGORY_CN = {
    "authenticity": "真伪",
    "capability": "能力",
    "compliance": "合规",
}

VERDICT_CN = {
    "passed_excellent": {"color": "#22c55e", "label": "PASSED_EXCELLENT", "cn": "优秀"},
    "passed": {"color": "#22c55e", "label": "PASSED", "cn": "通过"},
    "marginal": {"color": "#f59e0b", "label": "MARGINAL", "cn": "及格"},
    "failed": {"color": "#ef4444", "label": "FAILED", "cn": "不通过"},
}

BACKEND_CN = {
    "anthropic_direct": "Anthropic 直连",
    "bedrock_direct": "AWS Bedrock 直连",
    "kiro_proxy": "Kiro 代理链路",
    "vertex_proxy": "Vertex AI 代理",
    "unknown_proxy": "未知代理链路",
    "unknown": "未知",
}

def _serialize_report(report, protocol, degraded, degrade_reason, base_url: str = "") -> dict:
    """Convert DetectionReport to JSON-serializable dict."""
    verdict_key = report.verdict.value if hasattr(report.verdict, "value") else str(report.verdict)

    results = []
    for r in report.results:
        issues = []
        for iss in r.issues:
            issues.append({
                "level": iss.level.value if hasattr(iss.level, "value") else str(iss.level),
                "message": iss.message,
                "detector": iss.detector_name,
            })
        cat_val = r.category.value if hasattr(r.category, "value") else str(r.category)
        meta = DETECTOR_META.get(r.name, {})
        results.append({
            "name": r.name,
            "cn_name": meta.get("cn_name", r.name),
            "cn_desc": meta.get("cn_desc", ""),
            "category": cat_val,
            "category_cn": CATEGORY_CN.get(cat_val, cat_val),
            "score": round(r.score, 1),
            "weight": r.weight,
            "status": r.status,
            "cost_tokens": r.cost_tokens,
            "details": r.details,
            "issues": issues,
            "has_critical": r.has_critical,
        })

    verdict_info = VERDICT_CN.get(verdict_key, {"color": "#ef4444", "label": "UNKNOWN", "cn": "未知"})

    return {
        "model": report.model,
        "base_url": base_url,  # v2.5: 添加中转站网址
        "protocol": protocol.value if hasattr(protocol, "value") else str(protocol),
        "mode": report.mode,
        "degraded": degraded,
        "degrade_reason": degrade_reason,
        "total_score": round(report.total_score, 1),
        "verdict": verdict_key,
        "verdict_label": verdict_info["label"],
        "verdict_cn": verdict_info["cn"],
        "authenticity_score": round(report.authenticity_score, 1),
        "capability_score": round(report.capability_score, 1),
        "compliance_score": round(report.compliance_score, 1),
        "total_tokens": report.total_tokens,
        "total_requests": report.total_requests,
        "estimated_cost_usd": round(report.estimated_cost_usd, 4),
        "has_critical": report.has_critical,
        "backend_source": report.backend_source,
        "backend_source_cn": BACKEND_CN.get(report.backend_source, report.backend_source),
        "duration_seconds": round(report.duration_seconds, 1),
        "results": results,
    }

# ─── Provider presets (inspired by relayAPI) ─────────────────

_PROVIDER_PRESETS = [
    {"name": "Anthropic Official", "url": "https://api.anthropic.com/v1"},
    {"name": "OpenAI Official", "url": "https://api.openai.com/v1"},
    {"name": "Gemini Official", "url": "https://generativelanguage.googleapis.com/v1beta"},
    {"name": "OpenRouter", "url": "https://openrouter.ai/api/v1"},
    {"name": "DeepSeek Official", "url": "https://api.deepseek.com/v1"},
    {"name": "Moonshot (Kimi)", "url": "https://api.moonshot.cn/v1"},
    {"name": "Zhipu (GLM)", "url": "https://open.bigmodel.cn/api/paas/v4"},
    {"name": "Together AI", "url": "https://api.together.xyz/v1"},
    {"name": "Groq", "url": "https://api.groq.com/openai/v1"},
    {"name": "Fireworks AI", "url": "https://api.fireworks.ai/inference/v1"},
    {"name": "Mistral AI", "url": "https://api.mistral.ai/v1"},
    {"name": "Cerebras", "url": "https://api.cerebras.ai/v1"},
    {"name": "SambaNova", "url": "https://api.sambanova.ai/v1"},
    {"name": "Novita AI", "url": "https://api.novita.ai/v3/openai"},
    {"name": "SiliconFlow", "url": "https://api.siliconflow.cn/v1"},
]

@app.get("/api/providers")
def api_providers():
    return jsonify({"providers": _PROVIDER_PRESETS})

# ─── Evaluation endpoints ─────────────────────────────────────

from src.evaluation.reporter import result_to_dict as _eval_result_to_dict

_EVAL_JOBS: dict[str, dict] = {}
_EVAL_LOCK = threading.Lock()


@app.post("/api/evaluate")
def api_evaluate():
    """Submit model evaluation job."""
    data = request.get_json(force=True, silent=True) or {}
    base_url = (data.get("base_url") or "").strip()
    api_key = (data.get("api_key") or "").strip()
    models = data.get("models") or []
    difficulty = (data.get("difficulty") or "standard").strip().lower()
    dimensions = data.get("dimensions") or []  # 空=全部

    # 验证
    if not base_url.startswith(("http://", "https://")):
        return jsonify({"ok": False, "error": "base_url must start with http(s)://"}), 400
    # v2.8: SSRF 防护
    is_valid, err = _validate_base_url_no_ssrf(base_url)
    if not is_valid:
        return jsonify({"ok": False, "error": err}), 400
    if not api_key or len(api_key) < 8:
        return jsonify({"ok": False, "error": "api_key looks invalid"}), 400
    if not models or not isinstance(models, list):
        return jsonify({"ok": False, "error": "Please select at least one model"}), 400

    # 加载题库
    from src.evaluation.eval_engine import (
        EvaluationEngine, EvalDimension, EvalDifficulty,
        BASIC_LANGUAGE_QUESTIONS, TECHNICAL_QUESTIONS,
        ADVANCED_QUESTIONS, PRACTICAL_QUESTIONS, BOUNDARY_QUESTIONS,
    )

    dimension_map = {
        "basic_language": BASIC_LANGUAGE_QUESTIONS,
        "technical": TECHNICAL_QUESTIONS,
        "advanced_cognition": ADVANCED_QUESTIONS,
        "practical": PRACTICAL_QUESTIONS,
        "boundary": BOUNDARY_QUESTIONS,
    }

    if not dimensions:
        # 全部维度
        questions = []
        for dim_questions in dimension_map.values():
            questions.extend(dim_questions)
    else:
        questions = []
        for dim in dimensions:
            if dim in dimension_map:
                questions.extend(dimension_map[dim])

    # 按难度筛选
    if difficulty == "quick":
        from src.evaluation.eval_engine import QUICK_QUESTIONS
        questions = QUICK_QUESTIONS
    elif difficulty == "standard":
        from src.evaluation.eval_engine import STANDARD_QUESTIONS
        questions = STANDARD_QUESTIONS

    job_id = secrets.token_urlsafe(8)
    engine = EvaluationEngine(base_url, api_key)

    with _EVAL_LOCK:
        _EVAL_JOBS[job_id] = {
            "engine": engine,
            "models": models,
            "questions": questions,
            "status": "queued",
            "results": [],
            "progress": [],
            "error": None,
            "created_at": time.time(),
        }

    # 后台执行
    t = threading.Thread(
        target=_run_evaluation,
        args=(job_id, engine, models, questions),
        daemon=True,
    )
    t.start()

    return jsonify({"ok": True, "job_id": job_id, "total_questions": len(questions)})


def _run_evaluation(job_id: str, engine, models: list, questions: list):
    """后台执行测评任务"""
    with _EVAL_LOCK:
        job = _EVAL_JOBS.get(job_id)
        if not job:
            return
        job["status"] = "running"

    try:
        def on_progress(current, total, qid, score):
            with _EVAL_LOCK:
                j = _EVAL_JOBS.get(job_id)
                if j:
                    j["progress"].append({
                        "type": "progress",
                        "current": current,
                        "total": total,
                        "score": score,
                    })

        for model in models:
            with _EVAL_LOCK:
                j = _EVAL_JOBS.get(job_id)
                if j:
                    j["progress"].append({
                        "type": "model_start",
                        "model": model,
                    })

            result = engine.evaluate_model(model, questions, on_progress=on_progress)

            with _EVAL_LOCK:
                j = _EVAL_JOBS.get(job_id)
                if j:
                    j["results"].append(_eval_result_to_dict(result))
                    j["progress"].append({
                        "type": "model_done",
                        "model": model,
                    })

        with _EVAL_LOCK:
            j = _EVAL_JOBS.get(job_id)
            if j:
                j["status"] = "done"
                j["finished_at"] = time.time()

    except Exception as e:
        with _EVAL_LOCK:
            j = _EVAL_JOBS.get(job_id)
            if j:
                j["status"] = "error"
                j["error"] = str(e)
    finally:
        engine.close()


@app.get("/api/evaluate/status/<job_id>")
def api_eval_status(job_id: str):
    """Query evaluation job status."""
    with _EVAL_LOCK:
        job = _EVAL_JOBS.get(job_id)
    if job is None:
        return jsonify({"ok": False, "error": "Job not found"}), 404

    accept = request.headers.get("Accept", "")
    if "text/event-stream" in accept:
        return Response(
            stream_with_context(_eval_sse_stream(job_id)),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return jsonify({
        "ok": True,
        "job_id": job_id,
        "status": job["status"],
        "results": job["results"],
        "progress": job["progress"],
        "error": job["error"],
    })


def _eval_sse_stream(job_id: str):
    """SSE stream for evaluation progress."""
    last_idx = 0
    while True:
        with _EVAL_LOCK:
            job = _EVAL_JOBS.get(job_id)
            if job is None:
                break
            new_events = list(job["progress"][last_idx:])
            last_idx = len(job["progress"])
            is_done = job["status"] in ("done", "error")

        if job is None:
            yield f"event: error\ndata: {json.dumps({'error': 'Job not found'})}\n\n"
            return

        for evt in new_events:
            yield f"event: progress\ndata: {json.dumps(evt, ensure_ascii=False)}\n\n"

        if is_done:
            final = {
                "ok": True,
                "job_id": job_id,
                "status": job["status"],
                "results": job["results"],
                "error": job["error"],
            }
            yield f"event: complete\ndata: {json.dumps(final, ensure_ascii=False)}\n\n"
            return

        time.sleep(0.5)


# ─── Main page ────────────────────────────────────────────────

@app.route("/")
def index():
    """首页 - API检测"""
    return render_template("index.html")

@app.route("/evaluation")
def evaluation():
    """模型测评独立页面"""
    return render_template("evaluation.html")

@app.get("/health")
def health():
    return jsonify({"ok": True, "version": "2.8.5-web"})

# ── Entry point ──────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
