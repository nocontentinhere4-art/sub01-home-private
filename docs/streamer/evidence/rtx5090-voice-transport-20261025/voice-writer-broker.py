"""Finite UID1001 observer for exactly two coordinator-pinned FIFO producers."""
import argparse,json,os,signal,stat,time,traceback,runpy,hashlib
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--output',required=True);p.add_argument('--owner-base',required=True)
a=p.parse_args();config=Path(a.config);folder=Path(a.output)
if os.getuid()!=1001 or folder.is_symlink() or stat.S_IMODE(folder.stat().st_mode)!=0o700:raise SystemExit('UID/directory')
validator=Path('/tmp/sub01-share/voice-writer-proof-validation.py')
if hashlib.sha256(validator.read_bytes()).hexdigest()!='2bea39a3cf92ba05c9fc1fb84154521607bfd347b024e815c2e2557950eba63d':raise SystemExit('Validator changed')
validation=runpy.run_path(str(validator));targets=validation['read_file'](config)
if not validation['targets_ok'](targets):raise SystemExit('Target pins invalid/duplicate')
signal.signal(signal.SIGALRM,lambda *_:os._exit(124));signal.alarm(300)
start=time.monotonic()
while time.monotonic()-start<295:
 records=[]
 for target in targets:
  pid=target['pid'];ticks=target['ticks'];wanted=tuple(target['fifo'])
  row=dict(target,monotonic=time.monotonic(),state='X',writers=[],errors=[])
  try:
   before=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()
   if before[0] in ('Z','X','x') or int(before[19])!=ticks or Path(f'/proc/{pid}').stat().st_uid!=1001:raise RuntimeError('Target identity changed')
   fds=list(Path(f'/proc/{pid}/fd').iterdir())
   if len(fds)>1024:raise RuntimeError('FD cap')
   for fd in fds:
    try:
     s=fd.stat()
     if (s.st_dev,s.st_ino)!=wanted:continue
     flag=next(v.split()[1] for v in Path(f'/proc/{pid}/fdinfo/{fd.name}').read_text().splitlines() if v.startswith('flags:'))
     mode=int(flag,8)&3
     if mode in (1,2):row['writers'].append(dict(fd=int(fd.name),mode=mode))
    except (FileNotFoundError,ProcessLookupError):pass
   after=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()
   if after[0] in ('Z','X','x') or int(after[19])!=ticks:raise RuntimeError('Target identity changed during scan')
   row['state']=after[0]
  except Exception:row['errors'].append(traceback.format_exc());row['writers']=[]
  records.append(row)
 data=json.dumps(dict(monotonic=time.monotonic(),targets=records),separators=(',',':')).encode()
 if len(data)>65536:raise RuntimeError('Snapshot cap')
 temp=folder/'snapshot.tmp';temp.write_bytes(data);os.chmod(temp,0o600);os.replace(temp,folder/'snapshot.json')
 time.sleep(.1)
