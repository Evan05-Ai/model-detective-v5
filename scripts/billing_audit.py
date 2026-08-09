# -*- coding: utf-8 -*-
"""
计费审计脚本 - 完整走 billing_integrity + token_billing 检测器
用 utf-8 输出到文件，避免 GBK 编码问题
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 重定向 stdout/stderr 到 utf-8 文件
import io
OUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "billing_audit_result.txt")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from src.protocols.openai.client import OpenAIClient
from src.protocols.openai.detectors.billing_integrity import BillingIntegrityDetector
from src.protocols.openai.detectors.token_billing import TokenBillingDetector

BASE_URL = "https://api.qlhazycoder.top"
API_KEY = "sk-TNzA1LklDBsUBP7WFReFIlUis0pZTNfS2CYdKHQFmwTDnxTP"
MODEL = "claude-opus-4-8"

results = []

def log(msg=""):
    print(msg)
    results.append(msg)

# ====== 1. 先发一个极短请求看基础计费 ======
log("=" * 60)
log("  计费审计报告 - qlhazycoder.top")
log("=" * 60)
log()
log("  URL:  " + BASE_URL)
log("  模型: " + MODEL)
log("  协议: OpenAI 兼容")
log()

client = OpenAIClient(BASE_URL, API_KEY, MODEL)

# ====== 2. run billing_integrity detector ======
log("--- [1/3] BillingIntegrity 检测器 ---")
detector1 = BillingIntegrityDetector()
result1 = detector1.run(client)
log("  名称: " + result1.name)
log("  分数: " + str(result1.score) + "/100")
log("  状态: " + result1.status)
log("  Token: " + str(result1.cost_tokens))
log("  细节: " + result1.details)
for issue in result1.issues:
    log("  Issue[" + issue.level.value + "]: " + issue.message)
log()

# ====== 3. run token_billing detector ======
log("--- [2/3] TokenBilling 检测器 ---")
detector2 = TokenBillingDetector()
result2 = detector2.run(client)
log("  名称: " + result2.name)
log("  分数: " + str(result2.score) + "/100")
log("  状态: " + result2.status)
log("  Token: " + str(result2.cost_tokens))
log("  细节: " + result2.details)
for issue in result2.issues:
    log("  Issue[" + issue.level.value + "]: " + issue.message)
log()

# ====== 4. 手动精准计费审计 ======
log("--- [3/3] 手动精准计费审计 ---")
# 精确测试: "hi" 用 cl100k_base 算 token 数
try:
    import tiktoken
    enc = tiktoken.get_encoding("cl100k_base")
    actual_prompt_tokens = len(enc.encode("hi"))
    log("  tiktoken 精确计数: prompt 'hi' = " + str(actual_prompt_tokens) + " tokens")
except ImportError:
    actual_prompt_tokens = 1
    log("  tiktoken 不可用, 估算 'hi' = 1 token")

# 再发一次带完整 usage 审计的请求
import requests
session = requests.Session()
session.headers.update({
    "Authorization": "Bearer " + API_KEY,
    "Content-Type": "application/json",
})

# 测试1: extremal_minimal - 看系统有没有"最低消费"
payload1 = {
    "model": MODEL,
    "messages": [{"role": "user", "content": "a"}],
    "max_tokens": 1,
    "temperature": 0,
}
log('  测试1: 单字输入 "a", max_tokens=1')
resp1 = session.post(BASE_URL + "/v1/chat/completions", json=payload1, timeout=30)
if resp1.status_code == 200:
    d1 = resp1.json()
    u1 = d1.get("usage", {})
    log("    HTTP 200")
    log("    返回内容: " + repr(d1.get("choices", [{}])[0].get("message", {}).get("content", "")))
    log("    prompt_tokens=" + str(u1.get("prompt_tokens", 0)) +
        "  completion_tokens=" + str(u1.get("completion_tokens", 0)) +
        "  total_tokens=" + str(u1.get("total_tokens", 0)))
    # 检查是否和 "hi" 一样收 6484
    log("    [判定] " + ("prompt_tokens 固定 ~6500, 存在最低消费" if u1.get("prompt_tokens", 0) == 6484 else "prompt_tokens 会随输入变化"))
else:
    log("    HTTP " + str(resp1.status_code) + ": " + resp1.text[:200])

log()

# 测试2: empty-ish - 看看空消息 token 数
# 但 OpenAI 不允许空 messages, 所以用最短
payload2 = {
    "model": MODEL,
    "messages": [{"role": "user", "content": "hello world"}],
    "max_tokens": 5,
    "temperature": 0,
}
log('  测试2: 稍长输入 "hello world", max_tokens=5')
resp2 = session.post(BASE_URL + "/v1/chat/completions", json=payload2, timeout=30)
if resp2.status_code == 200:
    d2 = resp2.json()
    u2 = d2.get("usage", {})
    log("    HTTP 200")
    log("    prompt_tokens=" + str(u2.get("prompt_tokens", 0)) +
        "  completion_tokens=" + str(u2.get("completion_tokens", 0)) +
        "  total_tokens=" + str(u2.get("total_tokens", 0)))
    diff = u2.get("prompt_tokens", 0) - u1.get("prompt_tokens", 0)
    log("    与测试1的 prompt_tokens 差值: " + str(diff))
    if diff == 0:
        log("    [判定] 固定收费 ~6500 tokens, 与输入内容无关!")
    elif diff < 10:
        log("    [判定] 有最低消费, 额外输入仅增加很少")
    else:
        log("    [判定] 按实际输入长度浮动计费")
else:
    log("    HTTP " + str(resp2.status_code))

log()

# ====== 结论 ======
log("=" * 60)
log("  最终结论")
log("=" * 60)
log()

cost = client.get_cost_summary()
log("  总请求次数: " + str(cost["total_requests"]))
log("  总 Token: " + str(cost["total_tokens"]))
log("  估算费用: $" + "{:.6f}".format(cost["estimated_cost_usd"]))

# 综合判定
has_critical = False
for issue in result1.issues + result2.issues:
    if issue.level.value in ("critical", "major"):
        has_critical = True
        break

log()
conclusion_str = "  >>> 结论: "
if has_critical:
    conclusion_str += "计费: 不合理 (存在严重虚报)"
else:
    conclusion_str += "计费: 基本合理"
log(conclusion_str)

log()
log("=" * 60)

# 同时写入文件备份
with open(OUT_FILE, "w", encoding="utf-8") as f:
    f.write("\n".join(results))
log()
log("  结果已同时保存到: " + OUT_FILE)
