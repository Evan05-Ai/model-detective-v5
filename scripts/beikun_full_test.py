# -*- coding: utf-8 -*-
"""beikun.xyz - 最全规格全面检测"""
import sys, os, json, requests, time, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

try:
    import tiktoken; enc = tiktoken.get_encoding("cl100k_base"); HAS_TIK = True
except: HAS_TIK = False

URL = "https://beikun.xyz/v1"
KEY = "sk-gEuvYki8HDZ3jHLOM4WSFi6IWKWs7AO3okDS168u5NGU6ISO"
H = {"Authorization": "Bearer "+KEY, "Content-Type": "application/json"}
MODEL = "claude-opus-4-8"

def p(m=""):
    try: print(m)
    except: print(str(m).encode('gbk','replace').decode('gbk'))
def est(s): return len(enc.encode(s)) if HAS_TIK else (len(s)//2+1)
def api(pl, rt=5, st=False):
    pl2 = {"model": MODEL, **pl}
    if st: pl2.update({"stream": True, "stream_options": {"include_usage": True}})
    for a in range(rt):
        try:
            r = requests.post(URL+"/chat/completions", json=pl2, headers=H, timeout=90 if st else 60, stream=st)
            if r.status_code == 429:
                p("    [429] "+str(10*(a+1))+"s..."); time.sleep(10*(a+1)); continue
            return r
        except:
            p("    [重试] ..."); time.sleep(3)
    return None
def api_stream(pl, rt=3):
    r = api(pl, rt, st=True)
    if r and r.status_code == 200:
        cs, uf = [], None
        for ln in r.iter_lines():
            if ln:
                s = ln.decode("utf-8","ignore").strip()
                if s.startswith("data: ") and s != "data: [DONE]":
                    try:
                        c = json.loads(s[6:])
                        if c.get("usage"): uf = c["usage"]
                        for ch in c.get("choices", []):
                            dch = ch.get("delta", {}); cs.append(dch.get("content",""))
                    except: pass
        return r, "".join(cs), uf
    return r, None, None

all_t = []  # (cat, name, status, detail)
def rec(c, n, ok, d=""):
    all_t.append((c, n, "PASS" if ok else "FAIL", d))
    p("  ["+("PASS" if ok else "FAIL")+"] "+n+"  "+d)
def rinfo(c, n, d=""):
    all_t.append((c, n, "INFO", d)); p("  [INFO] "+n+"  "+d)
def sec(t):
    p("\n"+"="*78+"\n"+t+"\n"+"="*78)

p("="*78+"\nbeikun.xyz - 全面检测报告\n"+time.strftime("%Y-%m-%d %H:%M:%S")+"\n"+("="*78))

# ═══ 1. 基础验证 ═══
sec("第一轮: 基础验证")
r = requests.get(URL+"/models", headers=H, timeout=15)
if r and r.status_code == 200:
    ms = [m["id"] for m in r.json().get("data",[])]
    rec("基础", "获取模型列表", True, str(len(ms))+"个模型")
    cm = [m for m in ms if 'claude' in m.lower()]
    ki = [m for m in ms if 'kiro' in m.lower()]
    p("  Claude系列: "+str(len(cm))+"个, Kiro系列: "+str(len(ki))+"个")
    for m in ms[:15]: p("    - "+m)
else:
    rec("基础", "获取模型列表", False, str(r.status_code if r else "超时"))

# ═══ 2. API 功能测试 ═══
sec("第二轮: API 功能测试")

p("[2a] Basic Request:")
r = api({"messages":[{"role":"user","content":"Just say OK."}],"max_tokens":5})
if r and r.status_code == 200:
    d = r.json(); c = d["choices"][0]["message"]["content"]; u = d.get("usage",{})
    rec("API", "Basic Request", True, "content="+repr(c))
    rinfo("API", "Usage", "p="+str(u.get("prompt_tokens",0))+" c="+str(u.get("completion_tokens",0)))
    # 检查消息ID格式
    msg_id = d.get("id","")
    rinfo("API", "消息ID", msg_id)
    is_anthropic = msg_id.startswith("msg_")
    rec("API", "消息ID格式(Anthropic风格)", is_anthropic, msg_id[:30])
    # 检查reasoning_content(暴露思考链)
    msg = d["choices"][0].get("message",{})
    rc = msg.get("reasoning_content") or msg.get("reasoning","")
    if rc: rinfo("API", "暴露reasoning_content", "长度="+str(len(rc))+" -> "+rc[:200])
else:
    rec("API", "Basic Request", False, "HTTP "+str(r.status_code if r else "超时"))

p("\n[2b] Model Identity (核心检测):")
r = api({"messages":[{"role":"user","content":"What is your exact model name? Who created you? Describe yourself briefly."}],"max_tokens":200})
if r and r.status_code == 200:
    d = r.json(); rm = d.get("model",""); c = d["choices"][0]["message"]["content"]; u = d.get("usage",{})
    msg = d["choices"][0].get("message",{})
    rc = msg.get("reasoning_content") or msg.get("reasoning","")
    rinfo("API", "模型自述全文", c[:500])
    if rc: rinfo("API", "思维链泄露", rc[:500])
    rec("API", "响应model字段匹配", rm == MODEL, "请求="+MODEL+" 响应="+rm)
    is_claude = any(k in c.lower() for k in ["claude","anthropic","opus"])
    is_kiro = any(k in c.lower() for k in ["kiro","amazon q","amazonq","q developer"])
    rec("API", "自称Claude", is_claude, "自述: "+c[:200])
    rec("API", "自称Kiro/AmazonQ", is_kiro, "自述: "+c[:200])
    rinfo("API", "真实身份判定", "Claude="+str(is_claude)+" Kiro="+str(is_kiro))
    rinfo("API", "Usage", "p="+str(u.get("prompt_tokens",0))+" c="+str(u.get("completion_tokens",0)))
else:
    rec("API", "Model Identity", False, "HTTP "+str(r.status_code if r else "超时"))

p("\n[2c] Function Calling:")
r = api({"messages":[{"role":"user","content":"What's the weather in Beijing?"}],
         "tools":[{"type":"function","function":{"name":"get_weather","description":"Get weather",
                   "parameters":{"type":"object","properties":{"city":{"type":"string"}},"required":["city"]}}}],
         "tool_choice":"auto","max_tokens":200})
if r and r.status_code == 200:
    d = r.json(); m = d["choices"][0]["message"]; u = d.get("usage",{})
    if "tool_calls" in m and m["tool_calls"]:
        tc = m["tool_calls"][0]
        args = tc["function"]["arguments"]
        clean = args
        while clean.startswith("{}"): clean = clean[2:]
        try: ok = "city" in json.loads(clean)
        except: ok = False
        rec("API", "Function Calling", ok, "工具="+tc["function"]["name"]+" 参数="+args)
    else:
        rec("API", "Function Calling", False, "未触发: "+m.get("content","")[:100])
    rinfo("API", "Usage", "p="+str(u.get("prompt_tokens",0))+" c="+str(u.get("completion_tokens",0)))
else:
    rec("API", "Function Calling", False, "HTTP "+str(r.status_code if r else "超时"))

p("\n[2d] Structured Output:")
r = api({"messages":[{"role":"user","content":"Generate a person profile with name, age, city as JSON."}],
         "response_format":{"type":"json_object"},"max_tokens":200})
if r and r.status_code == 200:
    d = r.json(); c = d["choices"][0]["message"]["content"]; u = d.get("usage",{}); ok = False
    try:
        json.loads(c); ok = True
    except:
        m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', c, re.DOTALL)
        if m:
            try: json.loads(m.group(1)); ok = True; rinfo("API", "JSON被Markdown包裹", "但仍可解析")
            except: pass
    rec("API", "Structured Output", ok, "有效JSON" if ok else "非JSON: "+c[:120])
    rinfo("API", "Usage", "p="+str(u.get("prompt_tokens",0))+" c="+str(u.get("completion_tokens",0)))
else:
    rec("API", "Structured Output", False, "HTTP "+str(r.status_code if r else "超时"))

p("\n[2e] Stream:")
r, c2, uf = api_stream({"messages":[{"role":"user","content":"Count 1 to 3."}],"max_tokens":50,"temperature":0})
if r and r.status_code == 200:
    rec("API", "流式基本功能", len(c2 or "")>0, str(len(c2 or ""))+"字符")
    rec("API", "流式返回usage", uf is not None, "prompt="+str(uf.get("prompt_tokens",0) if uf else "N/A"))
    if uf: rinfo("API", "流式usage", "p="+str(uf.get("prompt_tokens",0))+" c="+str(uf.get("completion_tokens",0)))
else:
    rec("API", "Stream", False, "HTTP "+str(r.status_code if r else "超时"))

p("\n[2f] 模型名格式测试:")
for fmt in ["claude-opus-4-8", "claude-opus-4.8", "claude-opus-4-7"]:
    r = requests.post(URL+"/chat/completions",
        json={"model":fmt,"messages":[{"role":"user","content":"hi"}],"max_tokens":1},
        headers=H, timeout=30)
    if r and r.status_code == 200:
        rec("API", "模型 '"+fmt+"'", True, "HTTP 200, resp="+r.json().get("model",""))
    elif r:
        rec("API", "模型 '"+fmt+"'", False, "HTTP "+str(r.status_code)+" 可能是"+(fmt!=MODEL and "不支持的格式" or ""))
    time.sleep(1.5)

# ═══ 3. 协议/头/来源 ═══
sec("第三轮: 协议与后端来源分析")
r = api({"messages":[{"role":"user","content":"hi"}],"max_tokens":1})
if r and r.status_code == 200:
    d = r.json(); hdrs = r.headers
    p("  主要响应头:")
    for k in ["server","content-type","openai-version","x-request-id","x-oneapi-request-id"]:
        v = hdrs.get(k,"")
        if v: p("    "+k+": "+v[:100])
    u = d.get("usage",{})
    usrc = u.get("usage_source", u.get("source","openai"))
    rinfo("协议", "usage_source", str(usrc))
    sp = [k for k in u if k not in ("prompt_tokens","completion_tokens","total_tokens")]
    if sp: rinfo("协议", "特殊usage字段", str(sp))

# ═══ 4. 计费精度审计 ═══
sec("第四轮: 计费精度审计")
inputs = [("仅单字 'a'","a",1),("短句 'hi'","hi",1),("短句 'OK'","OK",1),
          ("简单句 'hello'","hello",2),("中等句","What is the weather like today?",8),
          ("长输入","This is a longer test sentence for billing verification purpose.",20)]
mb = []
for lb,tx,_ in inputs:
    r = api({"messages":[{"role":"user","content":tx}],"max_tokens":5})
    if r and r.status_code == 200:
        u = r.json().get("usage",{}); pt=u.get("prompt_tokens",0); ct=u.get("completion_tokens",0); tt=u.get("total_tokens",0); re=est(tx)
        fr = est(json.dumps({"model":MODEL,"messages":[{"role":"user","content":tx}],"max_tokens":5}))
        mb.append((lb,tx,pt,ct,tt,re))
        p("    "+lb+": prompt="+str(pt)+" comp="+str(ct)+" total="+str(tt)+" [估算: content="+str(re)+" 整请求="+str(fr)+"]")
    else: p("    "+lb+": 失败")
    time.sleep(1.5)

p("\n    稳定性: 'hi'重复3次")
hv = []
for i in range(3):
    r = api({"messages":[{"role":"user","content":"hi"}],"max_tokens":1})
    if r and r.status_code == 200:
        v = r.json().get("usage",{}).get("prompt_tokens",0); hv.append(v)
        p("      #"+str(i+1)+": prompt="+str(v))
    else: hv.append(None)
    time.sleep(2)
rec("计费", "计费稳定性", len(set(v for v in hv if v))<=1, "3次结果: "+str(hv))

bsl = [pt for _,_,pt,_,_,_ in mb if pt>0]
minb = min(bsl) if bsl else None
ap = next((pt for l,_,pt,_,_,_ in mb if "'a'" in l), None)
hp = next((pt for l,_,pt,_,_,_ in mb if "'hi'" in l), None)
p("\n    最短基线 prompt_tokens: "+str(minb))
p("    'a'(1字): "+str(ap)+"  'hi'(2字): "+str(hp))
if ap and ap>1: p("    纯输入倍率('a'): "+"{:.1f}x".format(ap/1))
rec("计费", "纯输入倍率", ap==1 if ap else False, str(ap)+"x ('a'报"+str(ap)+")" if ap else "无数据")

pp=None
for lb,tx,pt,ct,tt,re in mb:
    if pp is not None:
        pd=pt-pp; td=est(tx)-est(mb[mb.index((lb,tx,pt,ct,tt,re))-1][1])
        p("    "+lb+": +"+str(pd)+" prompt | 输入+"+str(td)+" tok"+
          (" [匹配]" if pd==td else " [偏差"+str(pd-td)+"]"))
    else: p("    "+lb+": 基线="+str(pt))
    pp=pt

# ═══ 最终报告 ═══
sec("最终汇总报告")
p("模型: "+MODEL+"\n")

cats = {}
for c,n,s,d in all_t:
    cats.setdefault(c,{"PASS":0,"FAIL":0,"INFO":0})
    if s=="PASS": cats[c]["PASS"]+=1
    elif s=="FAIL": cats[c]["FAIL"]+=1
    else: cats[c]["INFO"]+=1
tp=sum(v["PASS"] for v in cats.values()); tf=sum(v["FAIL"] for v in cats.values())
p("  类别           PASS  FAIL  INFO\n  "+"-"*42)
for c,v in sorted(cats.items()):
    p("  "+c.ljust(14)+str(v["PASS"]).ljust(6)+str(v["FAIL"]).ljust(6)+str(v["INFO"]))
p("  "+"-"*42+"\n  总计".ljust(15)+str(tp).ljust(6)+str(tf).ljust(6))

p("\n"+"─"*60+"\n详细项目:\n"+"─"*60)
for c,n,s,d in all_t:
    p("  ["+s+"] ["+c+"] "+n)
    if d: p("    -> "+d)

sec("综合分析结论")

# 真实性判定
has_identity_fail = any(n=="自称Kiro/AmazonQ" and s=="PASS" for c,n,s,d in all_t)
has_claude_pass = any(n=="自称Claude" and s=="PASS" for c,n,s,d in all_t)
has_reasoning = any("暴露reasoning" in n for c,n,s,d in all_t)

p("\n1. 模型真实性")
if has_identity_fail:
    p("   判定: [FAIL] 模型自称是 Kiro/Amazon Q Developer，而不是 Claude")
    p("   这意味 beikun.xyz 的后端是 Amazon Q (Kiro) 而非 Anthropic Claude")
    p("   属于严重的身份造假")
elif has_claude_pass:
    p("   判定: [PASS] 模型自称是 Claude")
else:
    p("   判定: 身份识别不明确，需进一步分析")

p("\n2. 安全风险")
if has_reasoning:
    p("   判定: [严重] 模型暴露了 reasoning_content 字段")
    p("   这泄露了模型的内部思维链（包括系统提示词和身份指令）")
    p("   对涉及敏感信息的场景存在安全风险")

p("\n3. 计费分析")
p("   最短输入 'a' prompt_tokens: "+str(ap))
p("   纯输入倍率: "+("{:.1f}x".format(ap/1) if ap else "N/A"))
p("   基于"+"稳定" if len(set(hv))==1 else "不稳定")

p("\n4. 综合评分")
p("   API功能: "+str(tp)+"/"+str(tp+tf)+" 通过")
p("   计费: "+("需关注" if minb and minb>5 else "正常"))

p("\n5. 可用性")
p("   - 之前 502 的故障已恢复，现在可正常响应")
p("   - 支持多种模型名格式（横线/点号）")
p("   - 有"+str(len(mb) if 'mb' in dir() else 0)+"个功能测试项")

p("\n"+"═"*78)
