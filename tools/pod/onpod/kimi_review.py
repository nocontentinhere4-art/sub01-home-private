import json,time,urllib.request,urllib.error,sys
R="/home/sub01-review-20261027"; name=sys.argv[1]
key=open("/home/unreal/.sub01-private/kimi-key").read().strip(); q=open(f"{R}/{name}-question.txt").read()
body={"model":"kimi-k3.1-pro","messages":[{"role":"user","content":q}],"max_tokens":12000,"reasoning_effort":"low"}
t0=time.time(); meta={"q_chars":len(q),"stream":False}
try:
    r=urllib.request.urlopen(urllib.request.Request("https://api.moonshot.ai/v1/chat/completions",data=json.dumps(body).encode(),method="POST",headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"}),timeout=280)
    d=json.loads(r.read().decode()); ch=d["choices"][0]; meta.update(http=200,finish=ch.get("finish_reason"),answer=(ch.get("message") or {}).get("content",""))
except urllib.error.HTTPError as e: meta.update(http=e.code,error=e.read().decode("utf-8","replace")[:400],retry_after=e.headers.get("Retry-After"))
except Exception as e: meta.update(error=f"{type(e).__name__}: {e}"[:300])
meta["seconds"]=round(time.time()-t0,1)
open(f"{R}/{name}-answer.json","w").write(json.dumps(meta,indent=1).replace(key,"<R>"))
print(json.dumps({k:v for k,v in meta.items() if k!="answer"}).replace(key,"<R>")); print(meta.get("answer","")[:1200])
