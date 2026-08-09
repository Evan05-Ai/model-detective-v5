# -*- coding: utf-8 -*-
"""beikun.xyz 快速连通测试"""
import sys, io, json, requests
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

URL = "https://beikun.xyz/v1/chat/completions"
KEY = "sk-gEuvYki8HDZ3jHLOM4WSFi6IWKWs7AO3okDS168u5NGU6ISO"
H = {"Authorization": "Bearer "+KEY, "Content-Type": "application/json"}

r = requests.post(URL, json={"model":"claude-opus-4-8","messages":[{"role":"user","content":"hi"}],"max_tokens":1}, headers=H, timeout=30)
print("Status:", r.status_code)
if r.status_code == 200:
    print("Response:", json.dumps(r.json(), ensure_ascii=False)[:500])
else:
    print("Body:", r.text[:500])
