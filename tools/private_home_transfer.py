"""Stream existing home assets privately between the authorized Runpod servers."""
import concurrent.futures,json,os,time,urllib.request,uuid
from pathlib import Path
DEADLINE=1791932256
ROOT=Path('/workspace/sub01-home-private')
c=json.loads(Path('/root/.sub01-home-private/source-transfer-session.json').read_text())
assert c['base_url']=='https://713u6mnmxu4y1a-8888.proxy.runpod.net'
token=next(iter(c['tokens'].values()));headers={'Authorization':'token '+token,'User-Agent':'Mozilla/5.0'}
def download(source,dest,parallel=1):
 url=c['base_url']+'/files/'+source;dest=Path(dest);dest.parent.mkdir(parents=True,exist_ok=True)
 with urllib.request.urlopen(urllib.request.Request(url,method='HEAD',headers=headers),timeout=30) as r:total=int(r.headers['Content-Length'])
 if dest.exists() and dest.stat().st_size==total:
  print('TRANSFER_ALREADY_COMPLETE',dest.name,total,flush=True);return
 print('TRANSFER_START',dest.name,total,flush=True)
 part=dest.with_name(dest.name+'.part');fd=os.open(part,os.O_CREAT|os.O_RDWR|os.O_TRUNC,0o600);os.ftruncate(fd,total)
 def segment(start,end):
  for attempt in range(3):
   position=start
   try:
    h={**headers,'Range':f'bytes={start}-{end}','Accept-Encoding':'identity','Cache-Control':'no-cache, no-store'}
    with urllib.request.urlopen(urllib.request.Request(url+'?sub01transfer='+uuid.uuid4().hex,headers=h),timeout=45) as r:
     if r.status!=206 and not (r.status==200 and start==0 and end==total-1):raise RuntimeError('Authenticated range transfer unsupported')
     if r.status==206 and r.headers.get('Content-Range')!=f'bytes {start}-{end}/{total}':raise RuntimeError('Incorrect authenticated response range')
     if int(r.headers.get('Content-Length','-1'))!=end-start+1:raise RuntimeError('Incorrect authenticated response length')
     while position<=end:
      if time.time()>=DEADLINE-20:raise RuntimeError('Home transfer budget deadline')
      data=r.read(min(1024*1024,end-position+1))
      if not data:raise RuntimeError('Truncated private transfer')
      written=os.pwrite(fd,data,position)
      if written!=len(data):raise RuntimeError('Partial destination write')
      position+=len(data)
    return end-start+1
   except Exception as e:
    if attempt==2:raise RuntimeError('Private transfer failed: '+type(e).__name__) from None
  raise RuntimeError('Private transfer failed')
 block=128*1024*1024;segments=[(i,min(total-1,i+block-1)) for i in range(0,total,block)];done=0
 try:
  with concurrent.futures.ThreadPoolExecutor(max_workers=parallel) as pool:
   futures=[pool.submit(segment,*x) for x in segments]
   for f in concurrent.futures.as_completed(futures):
    done+=f.result()
    if done==total or done//(1024**3)!=(done-f.result())//(1024**3):print('TRANSFER_PROGRESS',dest.name,done,total,flush=True)
  os.fsync(fd)
 finally:os.close(fd)
 if part.stat().st_size!=total:raise RuntimeError('Private transfer size mismatch')
 part.replace(dest);dest.chmod(0o600);print('TRANSFER_COMPLETE',dest.name,total,flush=True)
if __name__=='__main__':
 download('workspace/sub01-home-private/transfer-export/actual-project.tar',ROOT/'actual-project.tar',4)
 download('workspace/sub01-home-private/transfer-export/home-services.tar',ROOT/'home-services.tar',4)
 # Operator credentials are provisioned privately on rootfs; never transfer via volume.
 download('workspace/sub01-unreal/engine-full.zip',Path('/workspace/sub01-unreal/engine-full.zip'),8)
 print('ALL_EXISTING_HOME_ASSETS_TRANSFERRED',flush=True)
