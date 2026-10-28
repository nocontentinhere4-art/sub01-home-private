"""Read-only UID1001 /proc observations for its root-owned coordinator.
Only numeric identities, socket inodes, selected FIFO modes and BASE-match booleans
are returned. No arbitrary argv strings, filesystem paths or file contents.
"""
from pathlib import Path
import argparse,json,os,time
p=argparse.ArgumentParser();p.add_argument('--base',required=True);p.add_argument('--fifo',action='append',default=[])
a=p.parse_args()
if os.getuid()!=1001 or os.geteuid()!=1001:raise SystemExit('observer requires UID1001')
base=Path(a.base)
if not base.is_absolute():raise SystemExit('absolute diagnostic BASE required')
wanted={tuple(map(int,s.split(':')))for s in a.fifo};out={}
for d in Path('/proc').iterdir():
 if not d.name.isdigit():continue
 try:
  if d.stat().st_uid!=1001:continue
  parts=(d/'stat').read_text().rsplit(')',1)[1].split()
  ex=(d/'exe').stat();argv=(d/'cmdline').read_bytes().split(b'\0')
  sockets=[];fifos={}
  for fd in (d/'fd').iterdir():
   try:
    target=os.readlink(fd)
    if target.startswith('socket:[')and target.endswith(']'):sockets.append(target[8:-1])
    s=fd.stat();identity=s.st_dev,s.st_ino
    if identity in wanted:
     flags=next(x.split()[1]for x in (d/'fdinfo'/fd.name).read_text().splitlines()if x.startswith('flags:'))
     key=str(identity[0])+':'+str(identity[1]);fifos.setdefault(key,[]).append(int(flags,8)&3)
   except (FileNotFoundError,ProcessLookupError,StopIteration):pass
  out[d.name]={'ticks':int(parts[19]),'ppid':int(parts[1]),'sid':int(parts[3]),'exe':[ex.st_dev,ex.st_ino],
   'base_arg':any(os.fsencode(str(base))in s for s in argv),
   'recording_arg':any(os.fsencode(str(base/'director/recordings')+'/')in s for s in argv),
   'sockets':sockets,'fifos':fifos}
 except (FileNotFoundError,ProcessLookupError):pass
 # Any persistent access denial is visible, rather than silently claiming coverage.
 except PermissionError as e:out[d.name]={'observation_error':'PermissionError','errno':e.errno}
print(json.dumps({'uid':1001,'utc':time.time(),'processes':out}))
