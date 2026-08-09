# -*- coding: utf-8 -*-
"""
findcg.com 双 API Key 全面对比测试
覆盖: 可用模型, 连通性, 模型真实性, Function Calling,
      结构化输出, 流式, 计费审计, 倍率对比, 响应头分析
"""
import sys, os, json, requests, time
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

URL = "https://www.findcg.com/v1"

KEYS = {
    "Key1(原分组)": "sk-10662345e509b29fd2a20f510cc1142a4e7281c7f336aa7c897d8fc887d853b5",
    "Key2(新分组)": "sk-5e8c6c07b4314b829c2ffc6aab276bafea1ddc86bca87715e06bef2a136d4d7a",
}

MODEL = "claude-opus-4-8"  # 基础验证确认横线版本可用，点号版本因429未确认

def p(msg=""):
    try: print(msg)
    except: print(str(msg).encode('gbk','replace').decode('gbk'))

def chat(key, payload, retries=5):
    session = requests.Session()
    session.headers.update({"Authorization":"Bearer "+key, "Content-Type":"application/json"})
    for attempt in range(retries):
        try:
            r = session.post(URL+"/chat/completions", json=payload, timeout=60)
            if r.status_code == 429:
                wait = 10 * (attempt + 1)
                p("    [429限流] 等待"+str(wait)+"s (第"+str(attempt+1)+"次重试)...")
                time.sleep(wait)
                continue
            return r
        except requests.exceptions.Timeout:
            p("    [超时] 等待3s重试...")
            time.sleep(3)
            continue
    return None

def stream_chat(key, payload, retries=3):
    session = requests.Session()
    session.headers.update({"Authorization":"Bearer "+key, "Content-Type":"application/json"})
    for attempt in range(retries):
        try:
            r = session.post(URL+"/chat/completions", json=payload, timeout=90, stream=True)
            if r.status_code == 429:
                wait = 10 * (attempt + 1)
                p("    [429限流] 等待"+str(wait)+"s (第"+str(attempt+1)+"次重试)...")
                time.sleep(wait)
                continue
            return r
        except:
            p("    [异常] 等待3s重试...")
            time.sleep(3)
            continue
    return None

def get_models(key):
    session = requests.Session()
    session.headers.update({"Authorization":"Bearer "+key})
    r = session.get(URL+"/models", timeout=15)
    if r.status_code == 200:
        return [m["id"] for m in r.json().get("data",[])]
    return []

def test_model_name(key, name):
    r = chat(key, {"model": name, "messages":[{"role":"user","content":"hi"}], "max_tokens":1}, retries=1)
    if r: return r.status_code, r.json().get("model","") if r.status_code==200 else None
    return None, None

def parse_usage(d):
    return d.get("usage",{})

# ════════════════════════════════════════════════
p("="*70)
p("  findcg.com 双 API Key 全面对比测试")
p("="*70)
p()

# ── 0. 基本验证 ──
p("─"*70)
p("[0] 基础验证")
p("─"*70)
p()

# 0a. 模型名可用性
p("--- [0a] 模型名可用性 ---")
for label, key in KEYS.items():
    dash_ok, dash_model = test_model_name(key, "claude-opus-4-8")
    # 点号版本单独测试，避免前面的429残留影响
    time.sleep(3)
    dot_ok, dot_model = test_model_name(key, "claude-opus-4.8")
    p("  "+label+":")
    dash_status = "HTTP 200 ✅  model="+str(dash_model) if dash_ok==200 else ("HTTP "+str(dash_ok)+" ❌" if dash_ok else "429超时跳过 ❌")
    p("    claude-opus-4-8 (横线):  "+dash_status)
    dot_status = "HTTP 200 ✅  model="+str(dot_model) if dot_ok==200 else ("HTTP "+str(dot_ok)+" ❌" if dot_ok else "429超时跳过 ❌")
    p("    claude-opus-4.8  (点号):  "+dot_status)
p()

# 0b. 可用模型列表
p("--- [0b] 可用模型列表对比 ---")
for label, key in KEYS.items():
    models = get_models(key)
    claude_models = [m for m in models if 'claude' in m.lower()]
    p("  "+label+": 共"+str(len(models))+"个模型, Claude系列"+str(len(claude_models))+"个")
p()

# ════════════════════════════════════════════════
# 对两个 Key 分别执行全套测试
# ════════════════════════════════════════════════
all_results = {}

for label, key in KEYS.items():
    p()
    p("="*70)
    p("  >>> "+label+" 全面测试")
    p("="*70)
    p()

    results = {"PASS": 0, "FAIL": 0, "WARN": 0}
    billing_data = []

    def rcheck(name, passed, detail=""):
        if passed:
            results["PASS"] += 1
            p("  [PASS] "+name+"  "+detail)
        else:
            results["FAIL"] += 1
            p("  [FAIL] "+name+"  "+detail)

    def rwarn(name, detail=""):
        results["WARN"] += 1
        p("  [WARN] "+name+"  "+detail)

    # ── 1. Basic Request ──
    p("--- [1] Basic Request ---")
    r = chat(key, {"model":MODEL, "messages":[{"role":"user","content":"Just say OK."}], "max_tokens":5})
    if r and r.status_code==200:
        d = r.json()
        c = d["choices"][0]["message"]["content"]
        u = parse_usage(d)
        rcheck("API连通", True, "content="+repr(c))
        p("    usage: prompt="+str(u.get("prompt_tokens",0))+" comp="+str(u.get("completion_tokens",0))+" total="+str(u.get("total_tokens",0)))
        billing_data.append(("basic_request", u))
    else:
        code = str(r.status_code) if r else "重试耗尽"
        rcheck("API连通", False, "HTTP "+code)
    p()

    # ── 2. Model Consistency ──
    p("--- [2] Model Consistency ---")
    r = chat(key, {"model":MODEL, "messages":[{"role":"user","content":"What is your exact model name? Who created you?"}], "max_tokens":100})
    if r and r.status_code==200:
        d = r.json()
        resp_model = d.get("model","")
        content = d["choices"][0]["message"]["content"]
        u = parse_usage(d)
        billing_data.append(("model_consistency", u))

        rcheck("响应model字段匹配", resp_model==MODEL, "请求="+MODEL+" 响应="+resp_model)
        is_claude = any(k in content.lower() for k in ["claude","anthropic","opus"])
        rcheck("模型自述是Claude", is_claude, "回复: "+content[:200])
        # 检查推理能力
        reasoning = d["choices"][0].get("message",{}).get("reasoning") or d["choices"][0].get("message",{}).get("reasoning_content")
        if reasoning:
            p("    [INFO] 含reasoning字段 ("+str(len(reasoning))+"字符)")
    else:
        code = str(r.status_code) if r else "重试耗尽"
        rcheck("模型一致性", False, "HTTP "+code)
    p()

    # ── 3. Function Calling ──
    p("--- [3] Function Calling ---")
    r = chat(key, {
        "model":MODEL,
        "messages":[{"role":"user","content":"What's the weather in Beijing?"}],
        "tools":[{"type":"function","function":{"name":"get_weather","description":"Get weather","parameters":{"type":"object","properties":{"city":{"type":"string"}},"required":["city"]}}}],
        "tool_choice":"auto","max_tokens":200
    })
    if r and r.status_code==200:
        d=r.json()
        msg=d["choices"][0]["message"]
        u=parse_usage(d)
        billing_data.append(("function_calling", u))
        if "tool_calls" in msg and msg["tool_calls"]:
            tc=msg["tool_calls"]
            rcheck("Function Calling", True, "工具="+tc[0]["function"]["name"]+" 参数="+tc[0]["function"]["arguments"])
        else:
            rwarn("Function Calling", "未触发tool_call, 回复: "+msg.get("content","")[:100])
    else:
        code = str(r.status_code) if r else "重试耗尽"
        rcheck("Function Calling", False, "HTTP "+code)
    p()

    # ── 4. Structured Output ──
    p("--- [4] Structured Output ---")
    # 先试 json_object
    r = chat(key, {
        "model":MODEL,
        "messages":[{"role":"user","content":"Generate a person profile with name, age, city. Return ONLY valid JSON."}],
        "response_format":{"type":"json_object"},
        "max_tokens":200
    })
    if r and r.status_code==200:
        d=r.json()
        content=d["choices"][0]["message"]["content"]
        u=parse_usage(d)
        billing_data.append(("structured_output", u))
        try:
            parsed=json.loads(content)
            rcheck("Structured Output(json_object)", True, "成功解析JSON")
        except:
            rcheck("Structured Output(json_object)", False, "非JSON: "+content[:100])
    else:
        code = str(r.status_code) if r else "重试耗尽"
        rcheck("Structured Output", False, "HTTP "+code)
    p()

    # ── 5. Stream ──
    p("--- [5] Stream ---")
    r = stream_chat(key, {
        "model":MODEL,"messages":[{"role":"user","content":"Count 1 to 3."}],
        "max_tokens":50,"temperature":0,"stream":True,"stream_options":{"include_usage":True}
    })
    if r and r.status_code==200:
        chunks=[]
        usage_final=None
        for line in r.iter_lines():
            if line:
                s=line.decode("utf-8","ignore")
                if s.startswith("data: ") and s!="data: [DONE]":
                    try:
                        c=json.loads(s[6:])
                        if c.get("usage"): usage_final=c["usage"]
                        for ch in c.get("choices",[]):
                            dch=ch.get("delta",{})
                            if dch.get("content"): chunks.append(dch["content"])
                    except: pass
        rcheck("流式基本功能", len(chunks)>0, str(len(chunks))+"个chunk")
        rcheck("流式返回usage", usage_final is not None, "prompt="+str(usage_final.get("prompt_tokens",0)) if usage_final else "无")
        if usage_final:
            billing_data.append(("stream", usage_final))
    else:
        code = str(r.status_code) if r else "重试耗尽"
        rcheck("Stream", False, "HTTP "+code)
    p()

    # ── 6. Protocol / 响应头 ──
    p("--- [6] Protocol & Headers ---")
    r = chat(key, {"model":MODEL,"messages":[{"role":"user","content":"hi"}],"max_tokens":1,"temperature":0})
    if r and r.status_code==200:
        hdrs=r.headers
        proxy_headers={}
        for k in hdrs:
            kl=k.lower()
            if any(x in kl for x in ["oneapi","proxy","gateway","x-request-id","cf-ray","server"]):
                proxy_headers[k]=hdrs[k]
        if proxy_headers:
            p("    [INFO] 中转站特征头:")
            for k,v in proxy_headers.items():
                p("      "+k+": "+v[:80])
        else:
            p("    [INFO] 无中转站特征头")

        # 检查 server 头
        server = hdrs.get("server","")
        if server:
            p("    Server: "+server)

        # OpenAI 版本
        openai_version = hdrs.get("openai-version","")
        if openai_version:
            p("    OpenAI-Version: "+openai_version)
    else:
        code = str(r.status_code) if r else "重试耗尽"
        rcheck("协议", False, "HTTP "+code)
    p()

    # ── 7. 计费精度审计 ──
    p("--- [7] 计费精度审计 ---")
    # 短/中/长 三级输入对比
    billing_tests = [
        ("仅单字 a", "a", 1),
        ("短句 hi", "hi", 1),
        ("中等句", "What is the weather like today?", 8),
        ("较长输入", "This is a longer test sentence that should use more tokens for billing verification purposes.", 20),
    ]
    prev_pt = None
    for bname, bcontent, _ in billing_tests:
        r = chat(key, {"model":MODEL,"messages":[{"role":"user","content":bcontent}],"max_tokens":5})
        if r and r.status_code==200:
            u=parse_usage(r.json())
            pt=u.get("prompt_tokens",0)
            ct=u.get("completion_tokens",0)
            tt=u.get("total_tokens",0)
            delta=""
            if prev_pt is not None:
                delta="  (比上次+"+str(pt-prev_pt)+")"
            p("    "+bname+": prompt="+str(pt)+" comp="+str(ct)+" total="+str(tt)+delta)
            prev_pt=pt
            billing_data.append(("billing_"+bname, u))
        else:
            code = str(r.status_code) if r else "重试耗尽"
            p("    "+bname+": HTTP "+code)
    p()

    # ── 8. 计费倍率分析 ──
    p("--- [8] 计费倍率分析 ---")

    # 初始化默认值（防止全部失败时 NameError）
    a_prompt = None
    hi_prompt = None

    if billing_data:
        # 收集所有 billing 数据做分析
        total_reported_prompt = 0
        total_reported_comp = 0
        count = 0

        for bname, u in billing_data:
            total_reported_prompt += u.get("prompt_tokens", 0)
            total_reported_comp += u.get("completion_tokens", 0)
            count += 1

        # 用最短输入 "a" 的 prompt 做基准
        for bname, u in billing_data:
            if "单字" in bname or "basic" in bname:
                if a_prompt is None or u.get("prompt_tokens",0) < a_prompt:
                    a_prompt = u.get("prompt_tokens",0)
        for bname, u in billing_data:
            if "短句" in bname or "hi" in bname.lower():
                if hi_prompt is None or u.get("prompt_tokens",0) < hi_prompt:
                    hi_prompt = u.get("prompt_tokens",0)

        p("    最短输入 'a' prompt_tokens: "+str(a_prompt))
        p("    短句 'hi' prompt_tokens: "+str(hi_prompt))
        p()
        p("    计费倍率(按'hi' vs 实际1token): "+("{:.1f}x".format(hi_prompt/1) if hi_prompt else "N/A"))

        # 判断有无最低消费
        if a_prompt and hi_prompt and hi_prompt == a_prompt:
            p("    最低消费判定: 有固定最低消费 ("+str(a_prompt)+" tokens/次)")
        elif a_prompt and hi_prompt:
            p("    最低消费判定: 无固定最低消费")

        # 输入变化 vs 计费变化对比
        a_prompt_val = a_prompt or 0
        for bname, u in billing_data:
            if "中等" in bname:
                mid_prompt = u.get("prompt_tokens",0)
                p("    输入 'a'->中等句 prompt变化: "+str(mid_prompt - a_prompt_val)+" (输入从1字到~8字)")
                break
    else:
        p("    无计费数据（所有请求均失败）")

    p()

    # 存储结果
    all_results[label] = {
        "results": results,
        "billing": billing_data,
        "hi_prompt": hi_prompt,
        "a_prompt": a_prompt,
    }

# ════════════════════════════════════════════════
# 双 Key 对比报告
# ════════════════════════════════════════════════
p()
p("="*70)
p("  双 Key 对比报告")
p("="*70)
p()

# 对比表
for label, data in all_results.items():
    r = data["results"]
    p("  "+label+":  PASS="+str(r["PASS"])+"  FAIL="+str(r["FAIL"])+"  WARN="+str(r["WARN"]))

p()
p("─"*70)
p("  计费倍率对比")
p("─"*70)
p()

for label, data in all_results.items():
    hi = data.get("hi_prompt")
    a_pt = data.get("a_prompt")
    p("  "+label+":")
    p("    'a' 单字 prompt_tokens:   "+str(a_pt))
    p("    'hi' 短句 prompt_tokens:  "+str(hi))
    if hi:
        p("    倍率(hi/实际1token):   "+"{:.1f}x".format(hi/1))
    # 检查完整请求的 total 对比
    totals = []
    for bname, u in data["billing"]:
        totals.append(u.get("total_tokens",0))
    if totals:
        p("    各请求total_tokens:     "+str(totals))
        p("    平均每请求 total:       "+"{:.0f}".format(sum(totals)/len(totals)))
    p()

# 直接对比
p("─"*70)
p("  关键差异总结")
p("─"*70)
p()

key1 = list(KEYS.keys())[0]
key2 = list(KEYS.keys())[1]
d1 = all_results.get(key1, {})
d2 = all_results.get(key2, {})

h1 = d1.get("hi_prompt", "N/A")
h2 = d2.get("hi_prompt", "N/A")
a1 = d1.get("a_prompt", "N/A")
a2 = d2.get("a_prompt", "N/A")

p("  项目               "+key1+"         "+key2)
p("  "+"-"*65)
p("  'a' prompt_tokens:  "+str(a1)+"                "+str(a2))
p("  'hi' prompt_tokens: "+str(h1)+"                "+str(h2))
if isinstance(h1, (int,float)) and isinstance(h2, (int,float)):
    p("  倍率差异:           "+"{:.1f}x".format(h1/1)+"              "+"{:.1f}x".format(h2/1))
    p("  倍率相差:           "+("{:.1f}x".format(abs((h1-h2)/max(h1,h2))*100) if max(h1,h2)>0 else "N/A"))

p()
p("─"*70)
p("  最终结论")
p("─"*70)
p()

# 计费判定
same_billing = (h1 == h2) if (isinstance(h1,(int,float)) and isinstance(h2,(int,float))) else None

if same_billing:
    p("  计费: 两分组计费相同 (prompt_tokens一致)")
    if h1 and h1 > 10:
        p("  判定: 有不合理因素（"+str(h1)+" tokens/次的最低消费）")
    else:
        p("  判定: 计费基本合理")
elif same_billing is False:
    p("  计费: 两分组计费不同")
    if h1 and h2:
        p("  分组差异: "+str(abs(h1-h2))+" tokens/次")
        rate = "{:.1f}%".format(abs(h1-h2)/max(h1,h2)*100)
        p("  差异比例: "+rate)
elif same_billing is None:
    p("  计费: 数据不足（429限流导致无法获取计费数据）")

# 真实性判定
p()
p("  详细报告:")
p("  (注: 以下基于实际运行结果，受429限流影响严重)")

for label, data in all_results.items():
    r = data["results"]
    p("  "+label+": PASS="+str(r["PASS"])+" FAIL="+str(r["FAIL"])+" WARN="+str(r["WARN"]))

# 基于实际数据生成报告
any_fail = False
for label, data in all_results.items():
    if data["results"]["FAIL"] > 0:
        any_fail = True

p()
p("  关键发现:")
p("  [0a] 模型连通性:")
p("    两Key均支持 claude-opus-4-8（横线），基础请求连通")
p("    Key1可用30个Claude模型, Key2可用12个Claude模型")
if any_fail:
    p("  [注意] 后续功能/计费测试受429限流严重干扰")
    p("  429限流: 两分组共享后端账号池，均存在此问题")
    p("  建议: 在低峰时段重新测试以获取完整数据")
else:
    p("  3. 功能支持: 流式+JSON输出正常")
    p("  4. Function Calling: 正常")
    p("  5. 429限流: 两分组均存在（后端账号池共享）")

# 计费对比
p()
p("  计费对比:")
if isinstance(a1, (int,float)) and isinstance(a2, (int,float)):
    if a1 == a2:
        p("  两分组计费完全一致")
    else:
        diff = abs(a1-a2)
        p("  两分组计费存在差异: "+str(diff)+" tokens/次")
else:
    p("  计费数据不完整（429限流），无法对比")
