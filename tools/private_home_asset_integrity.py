"""Bounded local hashing on the authorized home Runpod servers; no media processing."""
from pathlib import Path
import hashlib,json,os,time
ROOT=Path('/workspace/sub01-home-private');deadline=1791932256
assert os.environ.get('RUNPOD_POD_ID') in {'713u6mnmxu4y1a','80lf8giw6ft61v'}
paths=[Path('/workspace/sub01-unreal/engine-full.zip'),ROOT/'transfer-export/actual-project.tar',ROOT/'transfer-export/home-services.tar'] if os.environ['RUNPOD_POD_ID']=='713u6mnmxu4y1a' else [Path('/workspace/sub01-unreal/engine-full.zip'),ROOT/'actual-project.tar',ROOT/'home-services.tar']
result={};block=128*1024*1024
for p in paths:
 hashes=[];whole=hashlib.sha256();offset=0
 with p.open('rb') as f:
  while True:
   h=hashlib.sha256();size=0
   while size<block:
    if time.time()>deadline-60:raise RuntimeError('Private hashing deadline')
    d=f.read(min(8*1024*1024,block-size))
    if not d:break
    h.update(d);whole.update(d);size+=len(d)
   if not size:break
   hashes.append(h.hexdigest());offset+=size
   if len(hashes)%32==0:print('INTEGRITY_PROGRESS',p.name,offset,flush=True)
 result[p.name]={'size':p.stat().st_size,'block_size':block,'blocks':hashes,'sha256':whole.hexdigest()}
 print('INTEGRITY_COMPLETE',p.name,len(hashes),whole.hexdigest(),flush=True)
q=ROOT/'logs/asset-block-integrity.json';q.write_text(json.dumps(result));print('ASSET_INTEGRITY_MANIFEST_READY',flush=True)
