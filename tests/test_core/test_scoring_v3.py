#!/usr/bin/env python3
"""v3.0 升级测试：评分引擎修复 + SSRF 重定向防护 + 检测器升级"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.evaluation.eval_engine import (
    EvalQuestion, EvalDimension, EvalDifficulty,
    score_answer, _match_keyword, _extract_option_letters,
    BASIC_LANGUAGE_QUESTIONS, TECHNICAL_QUESTIONS, ADVANCED_QUESTIONS,
    PRACTICAL_QUESTIONS, BOUNDARY_QUESTIONS, QUICK_QUESTIONS, STANDARD_QUESTIONS,
)
from src.protocols.base_client import ProtocolResponse, TokenUsage
from src.protocols.anthropic.detectors.thinking_signature import ThinkingSignatureDetector
from src.protocols.anthropic.detectors.integrity import IntegrityDetector
from src.protocols.openai.detectors.model_consistency import ModelConsistencyDetector
from src.utils.identity_analyzer import extract_identity, analyze_responses, _identity_matches_claimed
from src.core.http_utils import request_with_retry


def _q(rule_type, keywords=None, **rules):
    return EvalQuestion(
        id=999, dimension=EvalDimension.BASIC_LANGUAGE, difficulty=EvalDifficulty.FULL,
        title="test", prompt="test",
        expected_keywords=keywords or [],
        scoring_rules={"type": rule_type, **rules},
    )


# ==================== 评分引擎 v3.0 ====================

def test_keyword_word_boundary():
    """拉丁关键词词边界：B 不再子串误中 achievable"""
    q = _q("keyword_match", keywords=["B"], min_matches=1)
    r = score_answer(q, "This goal is achievable in theory")
    assert r["score"] == q.max_score * 0.3, f"B 不应子串匹配 achievable，实得 {r['score']}"
    print("  [OK] keyword word boundary")


def test_keyword_chinese_substring():
    """中文关键词仍为子串匹配"""
    q = _q("keyword_match", keywords=["北京", "上海"], min_matches=1)
    r = score_answer(q, "中国的首都是北京")
    assert r["score"] > 0
    print("  [OK] keyword chinese substring")


def test_option_correct_full_score():
    q = _q("option_match", keywords=["北京", "B"])
    r = score_answer(q, "答案是B)北京")
    assert r["score"] == q.max_score
    print("  [OK] option correct -> full score")


def test_option_wrong_low_score():
    """反关键词：明确选错选项只得 10%（旧版会因含字母得 70%）"""
    q = _q("option_match", keywords=["北京", "B"])
    r = score_answer(q, "我认为答案是A)上海")
    assert r["score"] <= q.max_score * 0.15, f"选错应≈10%，实得 {r['score']}"
    print("  [OK] option wrong -> ~10% score")


def test_option_letter_noise_zero():
    """回归关键用例：答案仅含普通英文单词（含字母 a/b/c/d）不得分"""
    q = _q("option_match", keywords=["北京", "B"])
    r = score_answer(q, "Artificial intelligence is a broad technology field")
    assert r["score"] == 0, f"普通英文含字母 a 不应得分，实得 {r['score']}"
    print("  [OK] option letter noise -> 0")


def test_option_listing_all():
    """复述全部选项 = 未作答，给 30% 而非满分"""
    q = _q("option_match", keywords=["北京", "B"])
    r = score_answer(q, "A)上海 B)北京 C)广州 D)深圳")
    assert r["score"] == q.max_score * 0.3
    print("  [OK] option listing-all -> 30%")


def test_option_contrast():
    """同时提及正确与错误选项（对比表述）-> 80%"""
    q = _q("option_match", keywords=["北京", "B"])
    r = score_answer(q, "A)上海不对，正确是B)北京")
    assert r["score"] == q.max_score * 0.8
    print("  [OK] option contrast -> 80%")


def test_extract_option_letters():
    assert _extract_option_letters("我选 b)") == {"b"}
    assert _extract_option_letters("option c is right") == {"c"}
    assert _extract_option_letters("achievable") == set()
    assert _extract_option_letters("[a] first") == {"a"}
    print("  [OK] extract option letters")


def test_exact_match_boundary():
    q = _q("exact_match", keywords=["391"])
    assert score_answer(q, "计算结果等于391。")["score"] == q.max_score
    assert score_answer(q, "等于3910")["score"] < q.max_score
    print("  [OK] exact match boundary")


def test_code_check_structure():
    """代码题：结构要素 + 题目要素命中率组合"""
    q = _q("code_check", keywords=["def", "pivot", "sort", "递归", "partition"])
    good = score_answer(q, """
    def quick_sort(arr):
        if len(arr) <= 1: return arr
        pivot = arr[0]
        left = [x for x in arr[1:] if x < pivot]
        return quick_sort(left) + [pivot] + quick_sort(rest)
    """)
    assert good["score"] >= q.max_score * 0.8, f"完整代码应≥80%，实得 {good['score']}"
    prose = score_answer(q, "快速排序是一种分治算法，需要递归实现")  # 无代码结构
    assert prose["score"] < q.max_score * 0.5
    print("  [OK] code check structure scoring")


def test_match_keyword_helper():
    assert _match_keyword("max", "maximum value") is False
    assert _match_keyword("max", "max(a, b)") is True
    # 注意：_match_keyword 约定接收已小写的答案（score_answer 内部先 lower）
    assert _match_keyword("H₂O", "水的化学式是h₂o") is True
    print("  [OK] _match_keyword helper")


# ==================== 题库与选题 ====================

def test_question_bank_counts():
    total = (len(BASIC_LANGUAGE_QUESTIONS) + len(TECHNICAL_QUESTIONS)
             + len(ADVANCED_QUESTIONS) + len(PRACTICAL_QUESTIONS) + len(BOUNDARY_QUESTIONS))
    assert total == 100
    assert len(QUICK_QUESTIONS) == 20
    assert len(STANDARD_QUESTIONS) == 40, f"Standard 应为 40 题（与 UI 文案一致），实际 {len(STANDARD_QUESTIONS)}"
    print("  [OK] question bank counts (100/20/40)")


def test_select_questions_dimensions_preserved():
    """P1-1 回归：维度选择不再被 difficulty 覆盖"""
    from web.app import _select_eval_questions
    qs = _select_eval_questions("quick", ["technical"])
    assert len(qs) == 4 and all(q.dimension.value == "technical" for q in qs)
    qs = _select_eval_questions("quick", [])
    assert len(qs) == 20
    qs = _select_eval_questions("standard", ["boundary"])
    assert len(qs) == 8 and all(q.dimension.value == "boundary" for q in qs)
    qs = _select_eval_questions("standard", [])
    assert len(qs) == 40
    qs = _select_eval_questions("full", ["technical"])
    assert len(qs) == 25
    print("  [OK] dimension selection preserved for quick/standard")


# ==================== identity_analyzer 关键词补充 ====================

def test_identity_glm_detected():
    """国产模型关键词：GLM 自报可识别为 opensource → 身份不匹配 20 分 + CRITICAL"""
    ext = extract_identity("I am GLM-4.6, developed by Zhipu AI.")
    assert ext.identity == "opensource" and ext.match_type == "positive"
    result = analyze_responses(
        responses=[{"strategy": 1, "response": "I am GLM-4.6, developed by Zhipu AI."}],
        claimed_model="claude-opus-4",
    )
    assert result.score <= 25
    assert any(i.level.value == "critical" for i in result.issues)
    print("  [OK] GLM/kimi keywords -> opensource mismatch")


def test_identity_claimed_o_series():
    """o3-mini 这类不含 gpt/openai 字样的声称模型不再误判身份不匹配"""
    assert _identity_matches_claimed("gpt", "o3-mini") is True
    assert _identity_matches_claimed("gpt", "gpt-4o") is True
    print("  [OK] claimed matching for o-series")


def test_identity_kimi_detected():
    ext = extract_identity("我是 Kimi，由 Moonshot AI 训练的模型。")
    assert ext.identity == "opensource"
    print("  [OK] kimi keyword detected")


# ==================== thinking_signature 特征分级 ====================

class _MockClient:
    def __init__(self, resp):
        self._resp = resp
        self.model = "claude-opus-4"
    def messages(self, **kwargs):
        return self._resp


def _sig_resp(headers):
    return ProtocolResponse(
        success=True, content="ok", model="claude-opus-4",
        headers=headers, usage=TokenUsage(total_tokens=100),
        thinking="thinking text", thinking_signature="sig==", raw_response={},
    )


def test_thinking_sig_single_cdn_header_not_proxy():
    """单一 CDN 弱特征（cf-ray）不再判为经中转 → 100 分"""
    det = ThinkingSignatureDetector()
    r = det.run(_MockClient(_sig_resp({"cf-ray": "8a9b"})))
    assert r.score == 100, f"仅 cf-ray 不应扣分，实得 {r.score}"
    print("  [OK] single CDN header -> direct (100)")


def test_thinking_sig_two_weak_headers_proxy():
    """≥2 个弱特征同时出现 → 判经中转 70 分"""
    det = ThinkingSignatureDetector()
    r = det.run(_MockClient(_sig_resp({"cf-ray": "8a9b", "x-ratelimit-limit": "100"})))
    assert r.score == 70, f"双弱特征应判中转 70，实得 {r.score}"
    print("  [OK] two weak headers -> proxied (70)")


def test_thinking_sig_strong_header_proxy():
    det = ThinkingSignatureDetector()
    r = det.run(_MockClient(_sig_resp({"x-oneapi-request-id": "abc"})))
    assert r.score == 70
    print("  [OK] strong header -> proxied (70)")


# ==================== integrity 空响应死逻辑修复 ====================

def test_integrity_empty_response_counted():
    det = IntegrityDetector()
    for i in range(4):
        det.observe({}, {"success": True, "model": "claude-opus-4",
                         "content": "hello" if i < 3 else ""}, "detector_x")
    r = det.finalize()
    assert any("响应内容为空" in i.message for i in r.issues), "空响应应被统计并扣分"
    print("  [OK] integrity empty response counted")


def test_integrity_thinking_only_not_counted():
    """thinking-only 响应（无文本块）不算空响应"""
    det = IntegrityDetector()
    for i in range(5):
        det.observe({}, {"success": True, "model": "claude-opus-4",
                         "content": "hello"}, "detector_x")
    det.observe({}, {"success": True, "model": "claude-opus-4",
                     "content": ""}, "thinking_signature")
    r = det.finalize()
    assert not any("响应内容为空" in i.message for i in r.issues)
    print("  [OK] thinking-only response excluded from empty count")


# ==================== system_fingerprint 检查 ====================

class _FpClient:
    model = "gpt-4o"
    def __init__(self, fps):
        self._fps = fps
        self._i = 0
    def chat(self, **kwargs):
        r = ProtocolResponse(
            success=True, content="A quiet machine dreams in light", model="gpt-4o",
            headers={}, usage=TokenUsage(total_tokens=50),
            raw_response={"system_fingerprint": self._fps[self._i]},
        )
        self._i += 1
        return r


def test_system_fingerprint_inconsistent():
    det = ModelConsistencyDetector()
    r = det.run(_FpClient(["fp_aaa", "fp_bbb"]))
    assert any("system_fingerprint 不一致" in i.message for i in r.issues)
    print("  [OK] inconsistent system_fingerprint flagged")


def test_system_fingerprint_consistent():
    det = ModelConsistencyDetector()
    r = det.run(_FpClient(["fp_aaa", "fp_aaa"]))
    assert any("system_fingerprint 一致" in i.message for i in r.issues)
    print("  [OK] consistent system_fingerprint noted")


# ==================== SSRF 重定向防护 ====================

class _FakeSession:
    def __init__(self):
        self.last_kwargs = None
    def request(self, method, url, **kwargs):
        self.last_kwargs = kwargs
        class _R:
            status_code = 200
            headers = {}
        return _R()


def test_request_with_retry_no_redirects():
    """request_with_retry 默认 allow_redirects=False（SSRF 重定向防护）"""
    s = _FakeSession()
    request_with_retry(s, "GET", "https://example.com/v1/models")
    assert s.last_kwargs.get("allow_redirects") is False
    print("  [OK] request_with_retry disables redirects")


def test_ssrf_validator_still_blocks_internal():
    from web.app import _validate_base_url_no_ssrf
    ok, _ = _validate_base_url_no_ssrf("http://127.0.0.1:5000")
    assert not ok
    ok, _ = _validate_base_url_no_ssrf("http://169.254.169.254/latest")
    assert not ok
    print("  [OK] SSRF validator still blocks internal addresses")


if __name__ == "__main__":
    import inspect
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("\nAll v3.0 scoring tests passed!")
