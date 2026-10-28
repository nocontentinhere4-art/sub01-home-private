#!/usr/bin/env python3
"""Private local console over one authenticated Jupyter terminal. No action retries."""
import argparse,asyncio,base64,json,secrets,ssl,sys
from pathlib import Path
import aiohttp
from aiohttp import web
from remote_relay import ALLOWED,MAX_REQUEST,MAX_RESPONSE
class Bridge:
 def __init__(self,pod_id,config,port):
  pods=json.loads(Path(config).read_text());pod=next(x for x in pods if x['id']==pod_id)
  self.secret=pod['env']['JUPYTER_PASSWORD'];self.base=f'https://{pod_id}-8888.proxy.runpod.net';self.port=port
  self.nonce=secrets.token_hex(24);self.prefix='SUB01RPC'+secrets.token_hex(16)+':'
  self.origin=f'http://127.0.0.1:{port}';self.terminal=None;self.session=None;self.ws=None;self.reader=None;self.lock=asyncio.Lock();self.pending={};self.ready=None;self.broken=False;self.queued=0
 async def start(self):
  sslctx=ssl.create_default_context(cafile='/root/.ccr/ca-bundle.crt')if Path('/root/.ccr/ca-bundle.crt').exists()else ssl.create_default_context()
  self.session=aiohttp.ClientSession(headers={'Authorization':'token '+self.secret},timeout=aiohttp.ClientTimeout(total=15),connector=aiohttp.TCPConnector(ssl=sslctx))
  async with self.session.post(self.base+'/api/terminals')as r:r.raise_for_status();self.terminal=(await r.json())['name']
  self.ws=await self.session.ws_connect(self.base+'/terminals/websocket/'+self.terminal,max_msg_size=4194304)
  self.ready=asyncio.get_running_loop().create_future();self.reader=asyncio.create_task(self.receive())
  source=Path(__file__).with_name('remote_relay.py').read_text()+'\nmain('+repr(self.prefix)+')\n'
  encoded=base64.b64encode(source.encode()).decode();command="python3 -u -c \"import base64;exec(base64.b64decode('"+encoded+"'))\"\n"
  await self.ws.send_str(json.dumps(['stdin','stty -echo -icanon -onlcr; export HISTFILE=/dev/null\n']));await asyncio.sleep(.5)
  await self.ws.send_str(json.dumps(['stdin',command]));await asyncio.wait_for(self.ready,15)
 async def receive(self):
  buffered=''
  try:
   async for msg in self.ws:
    if msg.type!=aiohttp.WSMsgType.TEXT:raise RuntimeError('terminal transport closed')
    data=json.loads(msg.data)
    if data[0]!='stdout':continue
    buffered+=data[1]
    if len(buffered)>4194304:raise ValueError('terminal frame bound')
    while '\n'in buffered:
     line,buffered=buffered.split('\n',1);line=line.rstrip('\r')
     if not line.startswith(self.prefix):continue
     answer=json.loads(line[len(self.prefix):])
     if answer.get('ready'):
      if not self.ready.done():self.ready.set_result(True)
     else:
      future=self.pending.pop(answer.get('id'),None)
      if future and not future.done():future.set_result(answer)
  except Exception:pass
  finally:
   self.broken=True
   for f in [self.ready,*self.pending.values()]:
    if f is not None and not f.done():f.set_exception(RuntimeError('terminal unavailable; no replay'))
 def route(self,method,path,host,origin):
  if host!=f'127.0.0.1:{self.port}':raise web.HTTPForbidden()
  if origin is not None and origin!=self.origin:raise web.HTTPForbidden()
  if method=='POST' and origin!=self.origin:raise web.HTTPForbidden()
  root='/'+self.nonce
  if not path.startswith(root+'/'):raise web.HTTPNotFound()
  target=path[len(root):]
  if (method,target)not in ALLOWED:raise web.HTTPNotFound()
  return target
 async def handle(self,request):
  if self.queued or self.lock.locked():raise web.HTTPTooManyRequests(text='Console busy; request not sent.')
  self.queued+=1
  try:return await asyncio.wait_for(self._handle(request),15)
  except asyncio.TimeoutError:raise web.HTTPGatewayTimeout(text='Console request timed out; do not replay an uncertain input.')
  finally:self.queued-=1
 async def _handle(self,request):
  target=self.route(request.method,request.path,request.host,request.headers.get('Origin'))
  if request.query_string:raise web.HTTPBadRequest(text='query not supported')
  if request.content_length is not None and request.content_length>MAX_REQUEST:raise web.HTTPRequestEntityTooLarge(max_size=MAX_REQUEST,actual_size=request.content_length)
  body=await asyncio.wait_for(request.read(),3)
  async with self.lock:
   if self.broken:raise web.HTTPBadGateway(text='Console transport disconnected; no action replay.')
   request_id=secrets.token_hex(12);f=asyncio.get_running_loop().create_future();self.pending[request_id]=f
   req={'id':request_id,'method':request.method,'path':target,'body':base64.b64encode(body).decode(),'etag':request.headers.get('If-None-Match','')}
   try:
    await self.ws.send_str(json.dumps(['stdin',json.dumps(req,separators=(',',':'))+'\n']))
    answer=await asyncio.wait_for(f,12)
   except Exception:
    self.broken=True;raise web.HTTPBadGateway(text='Request interrupted; action outcome unknown. No automatic retry.')
   finally:self.pending.pop(request_id,None)
  if 'error'in answer:raise web.HTTPBadGateway(text=answer['error'])
  raw=base64.b64decode(answer['body'],validate=True)
  if len(raw)>MAX_RESPONSE:raise web.HTTPBadGateway()
  if target=='/operator' and answer['status']==200:
   text=raw.decode('utf-8');text=text.replace("let token = '';","let token = 'local-console';").replace("token = sessionStorage.getItem(STORE) || '';","token = 'local-console';")
   # This is a nonsecret local UI sentinel, never the operator/Jupyter credential.
   text=text.replace('<input id="token"','<input hidden id="token"').replace('<button id="save"','<button hidden id="save"').replace('<button id="forget"','<button hidden id="forget"')
   begin=text.find('<p id="hint">');end=text.find('</p>',begin)
   if begin>=0 and end>=0:text=text[:begin]+'<p id="hint">Private local console. Log in directly on the Vagon page below. PC start remains under your control.</p>'+text[end+4:]
   raw=text.encode()
  headers=answer.get('headers',{});headers['Cache-Control']='no-store'
  return web.Response(status=answer['status'],body=raw,headers=headers)
 async def close(self):
  if self.ws:await self.ws.close()
  if self.reader:
   self.reader.cancel()
   try:await self.reader
   except BaseException:pass
  if self.session:
   try:
    if self.terminal:
     async with self.session.delete(self.base+'/api/terminals/'+self.terminal)as r:r.raise_for_status()
   finally:await self.session.close()
async def main(args):
 b=Bridge(args.pod,args.config,args.port);runner=None
 try:
  await b.start();app=web.Application(client_max_size=MAX_REQUEST);app.router.add_route('*','/{tail:.*}',b.handle)
  runner=web.AppRunner(app,access_log=None);await runner.setup();await web.TCPSite(runner,'127.0.0.1',args.port).start()
  print(b.origin+'/'+b.nonce+'/operator',flush=True)
  await asyncio.Event().wait()
 finally:
  if runner:await runner.cleanup()
  await b.close()
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--pod',default='505jw5ph3dt7ed');p.add_argument('--config',default=str(Path.home()/'.sub01/pods.json'));p.add_argument('--port',type=int,choices=[18838],default=18838);a=p.parse_args()
 try:asyncio.run(main(a))
 except KeyboardInterrupt:pass
 except Exception:print('Console bridge stopped; no request replay.',file=sys.stderr);sys.exit(1)
