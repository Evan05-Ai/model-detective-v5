# -*- coding: utf-8 -*-
"""
最小化计费检测脚本
目标：用最少的 token 检测 https://api.qlhazycoder.top 的计费真实性
策略：发 1 条超短请求（"hi" + max_tokens=1），分析 usage 字段
"""

import json
import requests
import sys

BASE_URL = "https://api.qlhazycoder.top"
API_KEY = "sk-TNzA1LklDBsUBP7WFReFIlUis0pZTNfS2CYdKHQFmwTDnxTP"
MODEL = "claude-opus-4-8"


def p(text=""):
    """兼容 GBK 编码的打印"""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='replace').decode('gbk'))


def test_openai_compatible():
    """尝试 OpenAI 兼容协议 - 发送最小请求"""
    p("=" * 60)
    p("[*] qlhazycoder.top 计费检测 (最小Token模式)")
    p("=" * 60)
    p("  URL:   " + BASE_URL)
    p("  模型:  " + MODEL)
    p("  协议:  OpenAI 兼容")
    p()

    session = requests.Session()
    session.headers.update({
        "Authorization": "Bearer " + API_KEY,
        "Content-Type": "application/json",
    })

    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 1,
        "temperature": 0,
    }

    p("  [>] 请求: messages=[user: hi], max_tokens=1")
    p()

    try:
        resp = session.post(
            BASE_URL + "/v1/chat/completions",
            json=payload,
            timeout=30,
        )
    except requests.exceptions.ConnectionError as e:
        p("  [X] 连接失败: " + str(e))
        p()
        return test_fallback(session)

    p("  [<] HTTP " + str(resp.status_code))
    p()

    if resp.status_code == 401:
        try:
            err = resp.json()
            p("  [X] 认证失败: " + json.dumps(err, ensure_ascii=False))
        except Exception:
            p("  [X] 认证失败: " + resp.text[:200])
        p()
        return test_fallback(session)

    if resp.status_code != 200:
        p("  [X] 请求失败: " + resp.text[:500])
        return

    data = resp.json()

    # 分析 usage
    usage = data.get("usage", {})
    choice = data.get("choices", [{}])[0]
    message = choice.get("message", {})
    content = message.get("content", "")

    reported_model = data.get("model", "N/A")
    reported_prompt = usage.get("prompt_tokens", 0)
    reported_completion = usage.get("completion_tokens", 0)
    reported_total = usage.get("total_tokens", 0)

    estimated_prompt = 1
    estimated_completion = 1
    estimated_total = estimated_prompt + estimated_completion

    multiplier = reported_total / max(estimated_total, 1)

    p("=" * 56)
    p("[=] 计费审计报告")
    p("=" * 56)
    p()
    p("  响应模型: " + str(reported_model))
    p("  返回内容: " + repr(content))
    p()
    p("  --- Token 审计 ---")
    p("  prompt_tokens:     上报=" + str(reported_prompt) +
      "  估算=" + str(estimated_prompt) +
      "  偏差=" + _dev_str(reported_prompt, estimated_prompt))
    p("  completion_tokens: 上报=" + str(reported_completion) +
      "  估算=" + str(estimated_completion) +
      "  偏差=" + _dev_str(reported_completion, estimated_completion))
    p("  total_tokens:      上报=" + str(reported_total) +
      "  估算=" + str(estimated_total) +
      "  偏差=" + _dev_str(reported_total, estimated_total))
    p()

    p("  --- 计费完整性 ---")
    if reported_total == reported_prompt + reported_completion:
        p("  total == prompt+completion: PASS")
    else:
        p("  total != prompt+completion: FAIL (" +
          str(reported_prompt) + "+" + str(reported_completion) +
          " != " + str(reported_total) + ")")

    cache_create = usage.get("cache_creation_input_tokens", 0)
    cache_read = usage.get("cache_read_input_tokens", 0)
    if cache_create or cache_read:
        p("  cache 字段: WARN (非缓存请求返回 cache)")
        p("    creation=" + str(cache_create) + " read=" + str(cache_read))
    else:
        p("  cache 字段: PASS")

    if reported_completion == 0 and content:
        p("  completion_tokens=0 但有内容: WARN (可能虚报)")

    p()
    p("  --- 计费倍率 ---")
    rating_str = "  倍率: " + "{:.2f}x".format(multiplier)
    if multiplier > 2.0:
        rating_str += "  [CRITICAL] 严重虚报!"
    elif multiplier > 1.5:
        rating_str += "  [MAJOR] 显著通胀"
    elif multiplier > 1.2:
        rating_str += "  [MINOR] 轻微通胀"
    else:
        rating_str += "  [OK] 透明"
    p(rating_str)

    p()
    p("  --- 费用估算 (官方: $15/$75 per 1M) ---")
    input_cost = reported_prompt * 15 / 1_000_000
    output_cost = reported_completion * 75 / 1_000_000
    p("  官方应收: $" + "{:.6f}".format(input_cost + output_cost))
    if multiplier > 1.0:
        p("  实收估算: $" + "{:.6f}".format((input_cost + output_cost) * multiplier))
    p()
    p("  --- 原始 usage ---")
    p("  " + json.dumps(usage, indent=2, ensure_ascii=False))
    p()
    p("=" * 56)
    p("[*] 本次消耗 " + str(reported_total) + " tokens")
    p("=" * 56)


def _dev_str(reported, estimated):
    if estimated <= 0:
        return "N/A"
    dev = (reported - estimated) / estimated * 100
    return "{:+.0f}%".format(dev)


def test_fallback(session=None):
    """尝试其它路径和协议"""
    p("=" * 56)
    p("[*] 尝试备用路径")
    p("=" * 56)
    p()

    if session is None:
        session = requests.Session()
        session.headers.update({
            "Authorization": "Bearer " + API_KEY,
            "Content-Type": "application/json",
        })

    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 1,
        "temperature": 0,
    }

    for path in ["/chat/completions", "/v1/chat/completions"]:
        url = BASE_URL + path
        p("  [>] POST " + url)
        try:
            resp = session.post(url, json=payload, timeout=30)
            p("  [<] HTTP " + str(resp.status_code))
            if resp.status_code == 200:
                data = resp.json()
                p("  [V] 成功! path=" + path)
                p("  usage: " + json.dumps(data.get("usage", {}), indent=2, ensure_ascii=False))
                return
            elif resp.status_code == 404:
                p("  [/] 路径不存在")
                continue
            else:
                p("  body: " + resp.text[:200])
        except Exception as e:
            p("  [X] " + str(e))

    p()
    p("  [*] 尝试 Anhtropic 协议...")
    test_anthropic()


def test_anthropic():
    """尝试 Anthropic 协议"""
    p("=" * 56)
    p("[*] Anthropic 协议")
    p("=" * 56)
    p()

    anthropic_headers = {
        "x-api-key": API_KEY,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }

    payload = {
        "model": MODEL,
        "max_tokens": 1,
        "messages": [{"role": "user", "content": "hi"}],
    }

    for path in ["/v1/messages", "/messages"]:
        url = BASE_URL + path
        p("  [>] POST " + url)
        try:
            resp = requests.post(url, json=payload, headers=anthropic_headers, timeout=30)
            p("  [<] HTTP " + str(resp.status_code))
            if resp.status_code == 200:
                data = resp.json()
                p("  [V] 成功!")
                usage = data.get("usage", {})
                p("  usage: " + json.dumps(usage, indent=2, ensure_ascii=False))
                return
            elif resp.status_code == 404:
                p("  [/] 路径不存在")
                continue
            else:
                p("  body: " + resp.text[:300])
        except Exception as e:
            p("  [X] " + str(e))


if __name__ == "__main__":
    test_openai_compatible()
