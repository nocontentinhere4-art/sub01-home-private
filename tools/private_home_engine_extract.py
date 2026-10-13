"""Extract the existing licensed engine archive only on the authorized recovery pod."""
from pathlib import Path
import concurrent.futures,os,shutil,stat,time,zipfile,threading
ROOT=Path('/workspace/sub01-unreal/UE');ARCHIVE=ROOT.parent/'engine-full.zip';DEADLINE=1791932256
assert os.environ.get('RUNPOD_POD_ID')=='80lf8giw6ft61v'
while not ARCHIVE.exists():
 if time.time()>DEADLINE-180:raise RuntimeError('Authorized extraction window ended')
 time.sleep(5)
ROOT.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(ARCHIVE) as z:
 entries=z.infolist();local=threading.local();print('EXTRACT_START',len(entries),sum(x.file_size for x in entries),flush=True)
 def extract_one(e):
  if not hasattr(local,'archive'):local.archive=zipfile.ZipFile(ARCHIVE)
  reader=local.archive
  if time.time()>=DEADLINE-30:raise RuntimeError('Private extraction deadline')
  relative=Path(e.filename)
  if relative.is_absolute() or '..' in relative.parts:raise RuntimeError('Invalid engine archive path')
  p=ROOT/relative;mode=e.external_attr>>16
  if e.is_dir():p.mkdir(parents=True,exist_ok=True);return 0
  p.parent.mkdir(parents=True,exist_ok=True)
  if stat.S_ISLNK(mode):
   target=reader.read(e).decode()
   if p.exists() or p.is_symlink():p.unlink()
   os.symlink(target,p)
  else:
   if p.exists():p.chmod(0o644)
   with reader.open(e) as source,p.open('wb') as target:shutil.copyfileobj(source,target,1024*1024)
   if mode&0o777:p.chmod(mode&0o777)
  return e.file_size
 def extract(e):
  try:return extract_one(e)
  except Exception as x:
   print('ENGINE_ENTRY_FAILED',e.filename,type(x).__name__,flush=True);raise
 count=0;size=0
 with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
  for n in pool.map(extract,entries):
   count+=1;size+=n
   if count%10000==0:print('EXTRACT_PROGRESS',count,size,flush=True)
 exe=ROOT/'Engine/Binaries/Linux/UnrealEditor'
 assert exe.is_file() and os.access(exe,os.X_OK)
 print('LICENSED_ENGINE_EXTRACT_COMPLETE',count,size,flush=True)
 (ROOT.parent/'engine-recovery-complete').write_text(str(size)+'\n')
