# -*- coding: utf-8 -*-
"""
findcg.com 真实性全面检测（不测计费）
覆盖: 基础请求, 模型一致性, 协议合规, Function Calling, 结构化输出, 流式, 身份认知
"""
import sys, os, json, requests, time
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

URL = "https://www.findcg.com/v1"
API_KEY = "sk-10662345e509b29fd2a20f510cc1142a4e7281c7f336aa7c897d8fc887d853b5"

# 注意: 用户请求 claude-opus-4-8 (横线) 但该站实际可用的是 claude-opus-4.8 (点号)
MODEL_PREFERRED = "claude-opus-4.8"   # dot version - works
MODEL_USER = "claude-opus-4-8"        # dash version - 404

H = {"Authorization": "Bearer " + API_KEY, "Content-Type": "application/json"}

def p(msg=""):
    try: print(msg)
    except: print(str(msg).encode('gbk','replace').decode('gbk'))

session = requests.Session()
session.headers.update(H)

def api(path, json_data, retries=3):
    """带重试的 API 调用，处理 429"""
    for attempt in range(retries):
        try:
            r = session.post(URL + path, json=json_data, timeout=45)
            if r.status_code == 429:
                wait = 5 * (attempt + 1)
                p("  [429 限流] 等待 "+str(wait)+"s...")
                time.sleep(wait)
                continue
            return r
        except requests.exceptions.Timeout:
            p("  [超时] 等待重试...")
            time.sleep(3)
            continue
    return None

def api_stream(path, json_data, retries=2):
    """流式请求，处理 429"""
    for attempt in range(retries):
        try:
            r = session.post(URL + path, json=json_data, timeout=60, stream=True)
            if r.status_code == 429:
                wait = 5 * (attempt + 1)
                p("  [429 限流] 等待 "+str(wait)+"s...")
                time.sleep(wait)
                continue
            return r
        except requests.exceptions.Timeout:
            time.sleep(3)
            continue
    return None

results = {"pass": 0, "fail": 0, "warn": 0}

def check(name, passed, detail=""):
    if passed:
        results["pass"] += 1
        p("  [PASS] "+name+"  "+detail)
    else:
        results["fail"] += 1
        p("  [FAIL] "+name+"  "+detail)

def warn(name, detail=""):
    results["warn"] += 1
    p("  [WARN] "+name+"  "+detail)

# ── 先测试 model name ──
p("="*60)
p("  findcg.com 真实性全面检测")
p("="*60)
p()
p("[Step 0] 模型名可用性验证")
for mname, label in [(MODEL_USER, "用户指定 claude-opus-4-8"), (MODEL_PREFERRED, "实际可用 claude-opus-4.8")]:
    r = requests.post(URL+"/chat/completions", json={"model": mname, "messages": [{"role":"user","content":"hi"}], "max_tokens": 1}, headers=H, timeout=15)
    if r.status_code == 200:
        p("  "+label+" -> HTTP 200 [可用]")
        actual_model = r.json().get("model","")
        if mname != actual_model:
            p("    响应 model 字段: "+actual_model)
    elif r.status_code == 404:
        p("  "+label+" -> HTTP 404 [不可用]")
    else:
        p("  "+label+" -> HTTP "+str(r.status_code))

MODEL = MODEL_PREFERRED
p("  将使用: "+MODEL)
p()

# ── 1. 基础请求 ──
p("--- [1/6] Basic Request (基础连通性) ---")
r = api("/chat/completions", {"model": MODEL, "messages": [{"role":"user","content":"Hello, respond with just 'OK'."}], "max_tokens": 10, "temperature": 0})
if r and r.status_code == 200:
    d = r.json()
    content = d["choices"][0]["message"]["content"]
    check("API 连通", True, "HTTP 200, 内容: "+repr(content))
else:
    code = str(r.status_code) if r else "重试耗尽"
    check("API 连通", False, "HTTP "+code)
p()

# ── 2. 模型一致性 ──
p("--- [2/6] Model Consistency (模型一致性) ---")
r = api("/chat/completions", {"model": MODEL, "messages": [{"role":"user","content":"Who created you? What is your exact model name?"}], "max_tokens": 100, "temperature": 0})
if r and r.status_code == 200:
    d = r.json()
    resp_model = d.get("model", "")
    model_field_match = resp_model == MODEL
    check("响应 model 字段匹配", model_field_match,
          "请求="+MODEL+", 响应="+resp_model)
    content = d["choices"][0]["message"]["content"]
    # 检查内容是否自称是 Claude
    mentions_claude = any(k in content.lower() for k in ["claude", "anthropic", "opus"])
    check("模型自述含 Claude/Anthropic", mentions_claude, "回复: "+content[:150])
else:
    code = str(r.status_code) if r else "重试耗尽"
    check("模型一致性", False, "HTTP "+code)
p()

# ── 3. Protocol (协议合规) ──
p("--- [3/6] Protocol (协议合规) ---")
# 检查响应头
r = api("/chat/completions", {"model": MODEL, "messages": [{"role":"user","content":"hi"}], "max_tokens": 1})
if r and r.status_code == 200:
    hdrs = r.headers
    # 检查 OneAPI / 中转站特征头
    proxy_headers = []
    for key in hdrs:
        kl = key.lower()
        if any(x in kl for x in ["oneapi", "proxy", "x-gateway", "x-proxy", "x-request-id", "cf-ray"]):
            proxy_headers.append((key, hdrs[key]))
    if proxy_headers:
        p("  中转站特征头: "+str(proxy_headers))
    else:
        p("  响应头: 标准 OpenAI 格式")
    # 检查 response 结构
    d = r.json()
    has_choices = "choices" in d and len(d["choices"]) > 0
    has_usage = "usage" in d
    check("响应结构合规 (choices+usage)", has_choices and has_usage,
          "choices="+str(len(d.get("choices",[])))+", usage="+str(d.get("usage","无")))
else:
    code = str(r.status_code) if r else "重试耗尽"
    check("协议合规", False, "HTTP "+code)
p()

# ── 4. Function Calling ──
p("--- [4/6] Function Calling (函数调用) ---")
tool_payload = {
    "model": MODEL,
    "messages": [{"role": "user", "content": "What's the weather in Beijing today?"}],
    "tools": [{
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get weather for a city",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "City name"},
                    "date": {"type": "string", "description": "Date"}
                },
                "required": ["city"]
            }
        }
    }],
    "tool_choice": "auto",
    "max_tokens": 200,
    "temperature": 0
}
r = api("/chat/completions", tool_payload)
if r and r.status_code == 200:
    d = r.json()
    msg = d["choices"][0]["message"]
    has_tc = "tool_calls" in msg and msg["tool_calls"] is not None
    if has_tc:
        tc = msg["tool_calls"]
        check("Function Calling", True,
              "调用工具: "+tc[0]["function"]["name"]+", 参数: "+tc[0]["function"]["arguments"])
    else:
        content = msg.get("content","")
        # 可能 LLM 直接回复了
        warn("Function Calling", "未触发 tool_call, 直接回复: "+content[:100])
else:
    code = str(r.status_code) if r else "重试耗尽"
    check("Function Calling", False, "HTTP "+code)
p()

# ── 5. Structured Output ──
p("--- [5/6] Structured Output (结构化输出) ---")
json_schema = {
    "name": "person_info",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer"},
            "city": {"type": "string"}
        },
        "required": ["name", "age", "city"],
        "additionalProperties": False
    }
}
r = api("/chat/completions", {
    "model": MODEL,
    "messages": [{"role": "user", "content": "Generate info for a person named Alice, 30 years old from Shanghai."}],
    "response_format": {"type": "json_object", "schema": json_schema},
    "max_tokens": 200,
    "temperature": 0
})
if r and r.status_code == 200:
    d = r.json()
    content = d["choices"][0]["message"]["content"]
    try:
        parsed = json.loads(content)
        has_keys = all(k in parsed for k in ["name", "age", "city"])
        check("Structured Output", has_keys,
              "解析结果: name="+str(parsed.get("name",""))+", age="+str(parsed.get("age",""))+", city="+str(parsed.get("city","")))
    except json.JSONDecodeError:
        check("Structured Output", False, "返回非 JSON: "+content[:100])
else:
    code = str(r.status_code) if r else "重试耗尽"
    warn("Structured Output (with schema)", "HTTP "+code+", 尝试 json_object 模式...")
    r2 = api("/chat/completions", {
        "model": MODEL,
        "messages": [{"role": "user", "content": "Return JSON: {\"name\":\"Alice\",\"age\":30,\"city\":\"Shanghai\"}"}],
        "response_format": {"type": "json_object"},
        "max_tokens": 200,
        "temperature": 0
    })
    if r2 and r2.status_code == 200:
        d2 = r2.json()
        content2 = d2["choices"][0]["message"]["content"]
        try:
            parsed2 = json.loads(content2)
            check("Structured Output (json_object)", True, "成功解析 JSON")
        except:
            check("Structured Output (json_object)", False, "返回非JSON: "+content2[:100])
    else:
        code2 = str(r2.status_code) if r2 else "重试耗尽"
        check("Structured Output", False, "HTTP "+code2)
p()

# ── 6. 流式 (Stream) ──
p("--- [6/6] Stream (流式支持) ---")
try:
    r = api_stream("/chat/completions", {
        "model": MODEL,
        "messages": [{"role": "user", "content": "Count from 1 to 5."}],
        "max_tokens": 100,
        "temperature": 0,
        "stream": True,
        "stream_options": {"include_usage": True}
    })
    if r and r.status_code == 200:
        chunks = []
        usage_final = None
        for line in r.iter_lines():
            if line:
                s = line.decode("utf-8","ignore")
                if s.startswith("data: ") and s != "data: [DONE]":
                    try:
                        c = json.loads(s[6:])
                        if c.get("usage"): usage_final = c["usage"]
                        for ch in c.get("choices",[]):
                            dch = ch.get("delta",{})
                            if dch.get("content"): chunks.append(dch["content"])
                    except: pass
        all_content = "".join(chunks)
        check("流式基本功能", len(chunks) > 0,
              "收到 "+str(len(chunks))+" 个 chunk, 内容长度 "+str(len(all_content)))
        check("流式返回 usage", usage_final is not None,
              "prompt="+str(usage_final.get("prompt_tokens",0)) if usage_final else "无")
        # 检查是否真的流式（多个 chunk）
        check("流式分块传输", len(chunks) > 1,
              "chunks="+str(len(chunks))+", 首chunk="+repr(chunks[0] if chunks else ""))
    elif r is None:
        check("流式支持", False, "重试耗尽")
    else:
        check("流式支持", False, "HTTP "+str(r.status_code))
except Exception as e:
    check("流式支持", False, "异常: "+str(e))
p()

# ── 报告 ──
p("="*60)
p("  测试报告")
p("="*60)
p()
total = results["pass"] + results["fail"] + results["warn"]
p("  测试项: "+str(total)+" | PASS: "+str(results["pass"])+" | FAIL: "+str(results["fail"])+" | WARN: "+str(results["warn"]))
p()

if results["fail"] == 0:
    p("  综合判定: 【通过】")
else:
    p("  综合判定: 【存在问题】")

p()
p("  ── 各项解读 ──")
p()
p("  1. Basic Request (连通性) — 检测中转站 API 是否可用")
p("     关键指标: HTTP 200, 正常返回内容")
p()
p("  2. Model Consistency (模型一致性) — 验证是否真的是目标模型")
p("     关键指标: 响应 model 字段匹配 + 模型自述匹配")
p()
p("  3. Protocol (协议合规) — 检查响应结构是否符合 OpenAI 标准")
p("     关键指标: 正确 choices/usage 格式, 有/无中转站特征头")
p()
p("  4. Function Calling (函数调用) — 是否支持 tool_use")
p("     关键指标: 正确返回 tool_calls, 参数格式正确")
p()
p("  5. Structured Output (结构化输出) — 是否支持 response_format")
p("     关键指标: 返回合法 JSON, 符合 schema")
p()
p("  6. Stream (流式支持) — 是否支持 SSE 流式回传")
p("     关键指标: 多个 chunk, 完整拼接内容, 含 usage 信息")
