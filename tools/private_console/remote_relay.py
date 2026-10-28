"""Fixed loopback desktop HTTP relay; launched only inside owned Jupyter terminal."""
import base64,http.client,json,sys
from pathlib import Path
ALLOWED={('GET','/operator'),('GET','/operator/frame.jpg'),('GET','/pc/state'),('POST','/operator/input'),('POST','/pc/vagon/arm'),('POST','/pc/vagon/start')}
MAX_REQUEST=16384;MAX_RESPONSE=2097152
SAFE_HEADERS={'content-type','etag','cache-control','content-security-policy','x-frame-options','referrer-policy'}
def relay(req,token,connection=http.client.HTTPConnection):
 method=req['method'];path=req['path']
 if (method,path)not in ALLOWED:raise ValueError('route refused')
 body=base64.b64decode(req.get('body',''),validate=True)
 if len(body)>MAX_REQUEST:raise ValueError('request bound')
 headers={'X-Admin-Token':token,'Content-Type':'application/json','Connection':'close'}
 if req.get('etag'):headers['If-None-Match']=req['etag'][:256]
 c=connection('127.0.0.1',8838,timeout=8)
 try:
  c.request(method,path,body=body,headers=headers);r=c.getresponse()
  if 300<=r.status<400 and r.status!=304:raise ValueError('redirect refused')
  data=r.read(MAX_RESPONSE+1)
  if len(data)>MAX_RESPONSE:raise ValueError('response bound')
  return {'status':r.status,'headers':{k:v for k,v in r.getheaders()if k.lower()in SAFE_HEADERS},'body':base64.b64encode(data).decode()}
 finally:c.close()
def main(prefix):
 token=(Path('/home/unreal/.sub01-private/operator-token').read_text()).strip()
 if len(token)<12:raise ValueError('operator credential unavailable')
 print(prefix+json.dumps({'ready':True}),flush=True)
 while True:
  line=sys.stdin.buffer.readline(32769)
  if not line:break
  if len(line)>32768:break
  req={}
  try:
   req=json.loads(line);request_id=req['id'];answer=relay(req,token);answer['id']=request_id
  except Exception:
   answer={'id':req.get('id') if 'req' in locals()else None,'error':'desktop request failed; action outcome may be unknown; no retry'}
  print(prefix+json.dumps(answer,separators=(',',':')),flush=True)
