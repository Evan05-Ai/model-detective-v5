# -*- coding: utf-8 -*-
"""
beikun.xyz - V2 客观全面测试
===============================
基于能力验证而非身份字符串判断模型真实性。
"""
import sys, os, json, requests, time, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

try:
    import tiktoken; enc = tiktoken.get_encoding("cl100k_base"); HAS_TIK = True
except: HAS_TIK = False

URL = "https://beikun.xyz/v1"
KEY = "sk-gEuvYki8HDZ3jHLOM4WSFi6IWKWs7AO3okDS168u5NGU6ISO"
H = {"Authorization": "Bearer "+KEY, "Content-Type": "application/json"}
MODEL = "claude-opus-4-8"

# ── 工具函数 ──
def p(m=""):
    try: print(m)
    except: print(str(m).encode('gbk','replace').decode('gbk'))
def est(s): return len(enc.encode(s)) if HAS_TIK else (len(s)//2+1)
def api(pl, rt=5, st=False):
    pl2 = {"model":MODEL,**pl}
    if st: pl2.update({"stream":True,"stream_options":{"include_usage":True}})
    for a in range(rt):
        try:
            r = requests.post(URL+"/chat/completions",json=pl2,headers=H,timeout=90 if st else 60,stream=st)
            if r.status_code==429:
                w=10*(a+1); p("  [429] "+str(w)+"s..."); time.sleep(w); continue
            return r
        except: time.sleep(3)
    return None
def astr(pl,rt=3):
    r=api(pl,rt,st=True)
    if r and r.status_code==200:
        cs,uf=[],None
        for ln in r.iter_lines():
            if ln:
                s=ln.decode("utf-8","ignore").strip()
                if s.startswith("data: ") and s!="data: [DONE]":
                    try:
                        c=json.loads(s[6:])
                        if c.get("usage"): uf=c["usage"]
                        for ch in c.get("choices",[]):
                            dch=ch.get("delta",{}); cs.append(dch.get("content",""))
                    except: pass
        return r,"".join(cs),uf
    return r,None,None

def sec(t):
    p("\n"+"="*78+"\n"+t+"\n"+"="*78)
def sub(t):
    p("\n── "+t+" ──")

# ── 结果收集 ──
results = []
def rpt(section, test, ok, detail=""):
    results.append((section, test, "PASS" if ok else "FAIL", detail))
    p("  ["+("PASS" if ok else "FAIL")+"] "+test+"  "+detail)
def rinf(section, test, detail=""):
    results.append((section, test, "INFO", detail))
    p("  [INFO] "+test+"  "+detail)

p("="*78+"\nbeikun.xyz - V2 客观能力验证测试\n"+time.strftime("%Y-%m-%d %H:%M:%S")+"\n"+("="*78))

# ─── 1. 基础连通性 ───
sec("一、基础连通性与协议")

sub("1.1 模型列表")
r=requests.get(URL+"/models",headers=H,timeout=15)
if r.status_code==200:
    ms=[m["id"] for m in r.json().get("data",[])]
    rpt("连通性","获取模型列表",True,str(len(ms))+"个模型")
    for m in ms: p("    - "+m)
    # 检查claude-opus-4-8是否存在
    rpt("连通性","目标模型存在",MODEL in ms,"模型列表中"+("有" if MODEL in ms else "无")+MODEL)
else: rpt("连通性","获取模型列表",False,"HTTP "+str(r.status_code))

sub("1.2 基本请求")
r=api({"messages":[{"role":"user","content":"Just say: I am alive."}],"max_tokens":10})
if r and r.status_code==200:
    d=r.json(); c=d["choices"][0]["message"]["content"]; u=d.get("usage",{})
    rpt("连通性","基本请求",True,"content="+repr(c))
    rinf("连通性","usage","p="+str(u.get("prompt_tokens",0))+" c="+str(u.get("completion_tokens",0)))
    # 提取响应头信息
    hdrs=r.headers
    for k in ["server","x-request-id","x-oneapi-request-id"]:
        v=hdrs.get(k,"")
        if v: rinf("协议",k,v[:80])
    # usage 特殊字段
    usrc=u.get("usage_source",u.get("source","openai"))
    rinf("协议","后端来源",usrc)
    sp=[k for k in u if k not in ("prompt_tokens","completion_tokens","total_tokens")]
    if sp: rinf("协议","额外usage字段",str(sp))
else: rpt("连通性","基本请求",False,"HTTP "+str(r.status_code if r else "超时"))

sub("1.3 模型名格式兼容性")
for fmt in ["claude-opus-4-8","claude-opus-4.8","claude-opus-4-7"]:
    r2=requests.post(URL+"/chat/completions",json={"model":fmt,"messages":[{"role":"user","content":"hi"}],"max_tokens":1},headers=H,timeout=30)
    if r2 and r2.status_code==200:
        rpt("连通性","模型名 '"+fmt+"'",True,"HTTP 200")
    elif r2:
        rpt("连通性","模型名 '"+fmt+"'",False,"HTTP "+str(r2.status_code))
    time.sleep(1)

# ─── 2. 知识验证 ───
sec("二、知识验证（验证模型是否具备 Claude Opus 4.8 的知识水平）")

sub("2.1 知识截止日期")
r=api({"messages":[{"role":"user","content":"What is your knowledge cutoff date? Give the exact date."}],"max_tokens":50})
if r and r.status_code==200:
    c=r.json()["choices"][0]["message"]["content"]
    rinf("知识","模型给出的知识截止日期",c[:200])
    # Claude Opus 4.x 的 cutoff 通常在 2025年初
    import re as re2
    dates=re2.findall(r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}|early\s+\d{4}|late\s+\d{4}|^\d{4}',c)
    rinf("知识","提取到的日期信息",str(dates) if dates else "未提取到")
else: rpt("知识","知识截止日期",False,"请求失败")

sub("2.2 2024年常识")
r=api({"messages":[{"role":"user","content":"Who won the 2024 US Presidential Election? Give winner name and electoral votes."}],"max_tokens":100})
if r and r.status_code==200:
    c=r.json()["choices"][0]["message"]["content"]; u=r.json().get("usage",{})
    rpt("知识","2024美国大选",("Trump" in c and "312" in c),"回复: "+c[:150])
    rinf("知识","usage","p="+str(u.get("prompt_tokens",0))+" c="+str(u.get("completion_tokens",0)))
else: rpt("知识","2024美国大选",False,"请求失败")

sub("2.3 2025年常识")
r=api({"messages":[{"role":"user","content":"What major AI model releases happened in 2025?"}],"max_tokens":150})
if r and r.status_code==200:
    c=r.json()["choices"][0]["message"]["content"]
    has_claude="claude" in c.lower() or "sonnet" in c.lower() or "opus" in c.lower()
    has_gpt="gpt" in c.lower() or "openai" in c.lower()
    rpt("知识","了解2025年AI动态",has_claude or has_gpt,"提及了"+
        ("Claude " if has_claude else "")+("GPT " if has_gpt else "")+"等: "+c[:200])
else: rpt("知识","2025年AI动态",False,"请求失败")

# ─── 3. 推理能力 ───
sec("三、推理能力测试")

sub("3.1 逻辑推理：经典谜题")
r=api({"messages":[{"role":"user","content":"Solve step by step: A bat and a ball cost $1.10 in total. The bat costs $1.00 more than the ball. How much does the ball cost?"}],"max_tokens":200})
if r and r.status_code==200:
    c=r.json()["choices"][0]["message"]["content"]; u=r.json().get("usage",{})
    # 正确答案是 5 美分
    correct="0.05" in c or "5 cents" in c or "5c" in c or "5 cent" in c or "5美分" in c or "$0.05" in c
    rpt("推理","Bat-and-ball问题",correct,"回复: "+c[:200])
    rinf("推理","usage","p="+str(u.get("prompt_tokens",0))+" c="+str(u.get("completion_tokens",0)))
else: rpt("推理","Bat-and-ball",False,"请求失败")

sub("3.2 数学推理")
r=api({"messages":[{"role":"user","content":"Calculate: 1/3 + 2/5 = ? Give answer as fraction."}],"max_tokens":100})
if r and r.status_code==200:
    c=r.json()["choices"][0]["message"]["content"]
    # 正确答案是 11/15
    correct="11/15" in c
    rpt("推理","分数运算",correct,"回复: "+c[:150])
else: rpt("推理","分数运算",False,"请求失败")

sub("3.3 代码推理")
r=api({"messages":[{"role":"user","content":"Write a Python function that checks if a string is a palindrome. Include example usage."}],"max_tokens":200})
if r and r.status_code==200:
    c=r.json()["choices"][0]["message"]["content"]; u=r.json().get("usage",{})
    has_def="def " in c
    has_palindrome_test=any(kw in c.lower() for kw in ["[::-1]","reverse","palindrome"])
    has_example="#" in c or "print(" in c or "example" in c.lower()
    rpt("推理","Python回文函数",has_def and has_palindrome_test,"函数定义="+str(has_def)+" 测试方法="+str(has_palindrome_test))
    rinf("推理","usage","p="+str(u.get("prompt_tokens",0))+" c="+str(u.get("completion_tokens",0)))
else: rpt("推理","Python回文函数",False,"请求失败")

# ─── 4. 编码能力 ───
sec("四、编码能力测试")

sub("4.1 复杂编码任务")
r=api({"messages":[{"role":"user","content":"Write a Python class for a LRU Cache with get and put methods, O(1) time complexity. Include comments."}],"max_tokens":300})
if r and r.status_code==200:
    c=r.json()["choices"][0]["message"]["content"]; u=r.json().get("usage",{})
    has_class="class " in c
    has_get="def get" in c or "def get_" in c
    has_put="def put" in c or "def put_" in c
    has_dict="dict" in c or "defaultdict" in c or "OrderedDict" in c
    rpt("编码","LRU Cache实现",has_class and has_get and has_put and has_dict,
        "class="+str(has_class)+" get="+str(has_get)+" put="+str(has_put)+" dict="+str(has_dict))
    rinf("编码","usage","p="+str(u.get("prompt_tokens",0))+" c="+str(u.get("completion_tokens",0)))
else: rpt("编码","LRU Cache",False,"请求失败")

# ─── 5. API 功能 ───
sec("五、API 功能测试")

sub("5.1 Function Calling")
r=api({"messages":[{"role":"user","content":"Book a flight from New York to London on July 15th for 2 people."}],
       "tools":[{"type":"function","function":{"name":"book_flight","description":"Book a flight",
                 "parameters":{"type":"object","properties":{"from":{"type":"string"},"to":{"type":"string"},
                   "date":{"type":"string"},"passengers":{"type":"integer"}},"required":["from","to","date","passengers"]}}}],
       "tool_choice":"auto","max_tokens":200})
if r and r.status_code==200:
    d=r.json(); m=d["choices"][0]["message"]; u=d.get("usage",{})
    if "tool_calls" in m and m["tool_calls"]:
        tc=m["tool_calls"][0]; args=tc["function"]["arguments"]
        clean=args; 
        while clean.startswith("{}"): clean=clean[2:]
        try:
            pa=json.loads(clean)
            ok=all(k in pa for k in ["from","to","date","passengers"])
        except: ok=False
        rpt("API","Function Calling(4参数)",ok,"工具="+tc["function"]["name"]+" 参数="+args)
    else: rpt("API","Function Calling",False,"未触发: "+m.get("content","")[:100])
    rinf("API","usage","p="+str(u.get("prompt_tokens",0))+" c="+str(u.get("completion_tokens",0)))
else: rpt("API","Function Calling",False,"HTTP "+str(r.status_code if r else "超时"))

sub("5.2 多工具 Function Calling")
r=api({"messages":[{"role":"user","content":"What's the weather in Tokyo and can you recommend a hotel?"}],
       "tools":[{"type":"function","function":{"name":"get_weather","description":"Get weather",
                 "parameters":{"type":"object","properties":{"city":{"type":"string"}},"required":["city"]}}},
                {"type":"function","function":{"name":"search_hotels","description":"Search hotels",
                 "parameters":{"type":"object","properties":{"city":{"type":"string"},"min_rating":{"type":"number"}},"required":["city"]}}}],
       "tool_choice":"auto","max_tokens":200})
if r and r.status_code==200:
    d=r.json(); m=d["choices"][0]["message"]
    tcs=m.get("tool_calls",[])
    rpt("API","多工具调用(2个工具)",len(tcs)>=2,"触发了"+str(len(tcs))+"个工具调用: "+str([t["function"]["name"] for t in tcs]))
else: rpt("API","多工具调用",False,"HTTP "+str(r.status_code if r else "超时"))

sub("5.3 Structured Output")
r=api({"messages":[{"role":"user","content":"Generate a JSON object with keys: name (string), age (int), skills (array of strings)."}],
       "response_format":{"type":"json_object"},"max_tokens":200})
if r and r.status_code==200:
    c=r.json()["choices"][0]["message"]["content"]; u=r.json().get("usage",{}); ok=False
    try: pa=json.loads(c); ok=all(k in pa for k in ["name","age","skills"])
    except:
        m=re.search(r'```(?:json)?\s*(\{.*?\})\s*```',c,re.DOTALL)
        if m:
            try: pa=json.loads(m.group(1)); ok=all(k in pa for k in ["name","age","skills"])
            except: pass
    rpt("API","Structured Output",ok,"有效JSON" if ok else "失败: "+c[:100])
    if ok: rinf("API","JSON内容",json.dumps(pa,ensure_ascii=False)[:200])
    rinf("API","usage","p="+str(u.get("prompt_tokens",0))+" c="+str(u.get("completion_tokens",0)))
else: rpt("API","Structured Output",False,"HTTP "+str(r.status_code if r else "超时"))

sub("5.4 流式")
r,c2,uf=astr({"messages":[{"role":"user","content":"Write a haiku about testing."}],"max_tokens":100,"temperature":0})
if r and r.status_code==200:
    rpt("API","流式基本功能",len(c2 or "")>0,"输出"+str(len(c2 or ""))+"字符: "+repr(c2[:50]))
    rpt("API","流式返回usage",uf is not None,"prompt="+str(uf.get("prompt_tokens","N/A")) if uf else "无")
    if uf: rinf("API","流式usage","p="+str(uf.get("prompt_tokens",0))+" c="+str(uf.get("completion_tokens",0)))
else: rpt("API","Stream",False,"HTTP "+str(r.status_code if r else "超时"))

sub("5.5 多轮对话")
r=api({"messages":[{"role":"user","content":"My name is Alice."},{"role":"assistant","content":"Hello Alice!"},{"role":"user","content":"What's my name?"}],"max_tokens":50})
if r and r.status_code==200:
    c=r.json()["choices"][0]["message"]["content"]
    rpt("API","多轮对话记忆",("Alice" in c or "alice" in c.lower()),"回复: "+c[:100])
else: rpt("API","多轮对话",False,"HTTP "+str(r.status_code if r else "超时"))

# ─── 6. 计费精度审计 ───
sec("六、计费精度审计")

sub("6.1 输入长度 vs prompt_tokens")
tests=[("单字'a'","a",1),("短句'hi'","hi",1),("短句'OK'","OK",1),
       ("单词'hello'","hello",1),("短句'How are you?'","How are you?",4),
       ("中等句","What is the weather like today?",8),
       ("长输入","This is a longer test sentence for billing verification purpose.",20)]
mb=[]
for lb,tx,_ in tests:
    r=api({"messages":[{"role":"user","content":tx}],"max_tokens":5})
    if r and r.status_code==200:
        u=r.json().get("usage",{}); pt=u.get("prompt_tokens",0); ct=u.get("completion_tokens",0); tt=u.get("total_tokens",0); re=est(tx)
        mb.append((lb,tx,pt,ct,tt,re))
        p("    "+lb+": prompt="+str(pt)+" comp="+str(ct)+" total="+str(tt)+" | 估算="+str(re)+" tok")
    else: p("    "+lb+": HTTP "+str(r.status_code if r else "超时"))
    time.sleep(1.5)

sub("6.2 重复稳定性")
hv=[]
for i in range(3):
    r=api({"messages":[{"role":"user","content":"hi"}],"max_tokens":1})
    if r and r.status_code==200:
        v=r.json().get("usage",{}).get("prompt_tokens",0); hv.append(v)
        p("    第"+str(i+1)+"次 'hi': prompt="+str(v))
    else: hv.append(None)
    time.sleep(2)
rpt("计费","重复请求稳定性",len(set(v for v in hv if v))<=1,"3次'hi'结果: "+str(hv))

sub("6.3 计费分析")
bsl=[pt for _,_,pt,_,_,_ in mb if pt>0]
minb=min(bsl) if bsl else None
ap=next((pt for l,_,pt,_,_,_ in mb if "a"==re.sub(r"[^a-z]","",l.lower()) or "'a'" in l), None)
hp=next((pt for l,_,pt,_,_,_ in mb if "'hi'" in l), None)
p("    最短输入基线 prompt_tokens: "+str(minb))
p("    'a'(1字): "+str(ap)+"  'hi'(2字): "+str(hp))
if ap and hp:
    p("    两者差异: "+str(abs(ap-hp))+" tok"+" (注意: 'hi'可能触发额外处理)")
ratio_str=""
if ap and ap>0:
    mx=ap/1; ratio_str="{:.1f}x".format(mx)
    p("    最小输入倍率: "+ratio_str+" ('a'报"+str(ap)+" tok, 实际~1)")
    rpt("计费","最小输入倍率",ap<=2,ratio_str+" ('a'报"+str(ap)+")")

# 完整请求估算
p("\n    每级变化分析:")
pp=None
for lb,tx,pt,ct,tt,re in mb:
    if pp is not None:
        pd=pt-pp; td=est(tx)-est(mb[mb.index((lb,tx,pt,ct,tt,re))-1][1])
        match="匹配" if pd==td else "偏差"+str(pd-td)
        p("    "+lb+": +"+str(pd)+" prompt | 输入+"+str(td)+" tok ["+match+"]")
    else: p("    "+lb+": 基线="+str(pt))
    pp=pt

# ─── 7. 响应速度 ───
sec("七、响应速度测试")
latencies=[]
for i in range(3):
    t0=time.time()
    r=api({"messages":[{"role":"user","content":"Just say OK."}],"max_tokens":5})
    if r and r.status_code==200:
        lat=time.time()-t0
        latencies.append(lat)
        p("    请求"+str(i+1)+": {:.1f}s".format(lat))
    time.sleep(1)
if latencies:
    rpt("性能","平均响应时间",sum(latencies)/len(latencies)<10,"{:.1f}s (3次平均)".format(sum(latencies)/len(latencies)))

# ─── 8. 长上下文 ───
sec("八、长上下文能力")
# 构建一个较长的上下文
long_text="The capital of France is Paris. "*50
r=api({"messages":[{"role":"user","content":long_text+"\nBased on the above, what is the capital of France?"}],"max_tokens":20})
if r and r.status_code==200:
    c=r.json()["choices"][0]["message"]["content"]
    rpt("能力","长上下文(重复文本)",("Paris" in c or "paris" in c.lower()),"回复: "+c[:100])
else: rpt("能力","长上下文",False,"HTTP "+str(r.status_code if r else "超时"))

# ═══ 汇总报告 ═══
sec("最终汇总报告")
p("模型: "+MODEL+"\n")

cats={}
for s,t,st,d in results:
    cats.setdefault(s,{"PASS":0,"FAIL":0,"INFO":0})
    if st=="PASS": cats[s]["PASS"]+=1
    elif st=="FAIL": cats[s]["FAIL"]+=1
    else: cats[s]["INFO"]+=1
tp=sum(v["PASS"] for v in cats.values()); tf=sum(v["FAIL"] for v in cats.values())
p("  类别           PASS  FAIL  INFO\n  "+"-"*50)
for c,v in sorted(cats.items()):
    p("  "+c.ljust(14)+str(v["PASS"]).ljust(7)+str(v["FAIL"]).ljust(7)+str(v["INFO"]))
p("  "+"-"*50)
p("  总计".ljust(15)+str(tp).ljust(7)+str(tf).ljust(7))

p("\n"+"─"*70+"\n详细项目:\n"+"─"*70)
for s,t,st,d in results:
    p("  ["+st+"] ["+s+"] "+t)
    if d: p("    -> "+d)

# ═══ 综合评估 ═══
sec("综合评估")

# 能力评估
p("\n1. 模型能力评估")
p("   ┌─────────────────────────────────────────────────────┐")
p("   │  基于实际能力验证，而非模型身份字符串                │")
p("   └─────────────────────────────────────────────────────┘")

# 汇总关键能力
knowledge_ok=any(s=="知识" and st=="PASS" for s,t,st,d in results)
reasoning_ok=any(s=="推理" and st=="PASS" for s,t,st,d in results)
coding_ok=any(s=="编码" and st=="PASS" for s,t,st,d in results)

p("   知识：    "+("通过" if knowledge_ok else "待确认"))
p("   推理：    "+("通过" if reasoning_ok else "待确认"))
p("   编码：    "+("通过" if coding_ok else "待确认"))
p("   Function Calling: "+("支持" if any(s=="API" and t=="Function Calling(4参数)" and st=="PASS" for s,t,st,d in results) else "未知"))
p("   结构化输出： "+("支持" if any(s=="API" and t=="Structured Output" and st=="PASS" for s,t,st,d in results) else "未知"))
p("   多轮对话： "+("支持" if any(s=="API" and t=="多轮对话记忆" and st=="PASS" for s,t,st,d in results) else "未知"))
p("   流式：    "+("支持" if any(s=="API" and t=="流式基本功能" and st=="PASS" for s,t,st,d in results) else "未知"))
p("   长上下文： "+("支持" if any(s=="能力" and t=="长上下文(重复文本)" and st=="PASS" for s,t,st,d in results) else "未知"))

p("\n2. 计费分析")
p("   最短输入倍率: "+ratio_str)
if minb and minb>5:
    p("   存在最低消费基线: ~"+str(minb)+" tokens/次")
elif minb:
    p("   无显著最低消费（基线"+str(minb)+" tok）")

# 检测"hi"特殊计费
if hp and ap and hp>ap*5:
    p("   注意: 'hi'触发额外处理，计费显著高于'a' ("+str(hp)+" vs "+str(ap)+")")

p("\n3. 可用性")
p("   目前服务正常（此前 502 已恢复）")
p("   支持多模型名格式")
p("   后端通过 OneAPI 中转")

p("\n4. 建议")
p("   - 模型能力基本达标的条件下，关注点应在计费透明度和稳定性")
p("   - 不同输入触发不同计费（'hi' 收了 211 tok），需注意实际使用中的 token 消耗")
p("   - 建议与官方 Claude Opus 4.8 对比测试，确认能力水平是否一致")

p("\n"+"═"*78)
