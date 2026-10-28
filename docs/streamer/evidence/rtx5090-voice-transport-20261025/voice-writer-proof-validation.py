"""Pure fail-closed validation shared by coordinator and diagnostic launcher."""
import json,stat,math
def read_file(path):
 s=path.lstat()
 if not stat.S_ISREG(s.st_mode) or s.st_uid!=1001 or stat.S_IMODE(s.st_mode)!=0o600 or s.st_size>65536:raise ValueError('Proof-file identity/size')
 return json.loads(path.read_bytes())
def targets_ok(targets):
 try:
  if type(targets) is not list or any(type(t) is not dict for t in targets):return False
  if len(targets)!=2 or {t['role'] for t in targets}!={'native','voice'}:return False
  if len({t['pid'] for t in targets})!=2 or len({tuple(t['fifo']) for t in targets})!=2:return False
  for t in targets:
   if type(t['pid']) is not int or t['pid']<=1 or type(t['ticks']) is not int or t['ticks']<=0:return False
   if len(t['fifo'])!=2 or any(type(v) is not int or v<0 for v in t['fifo']):return False
  native=next(t for t in targets if t['role']=='native')
  return (native['pid'],native['ticks'],tuple(native['fifo']))==(29950,53274039,(67,6480385251))
 except (KeyError,ValueError,TypeError,StopIteration):return False
def valid(body,target,now):
 try:
  if type(body) is not dict or type(body.get('monotonic')) not in (int,float) or not math.isfinite(body['monotonic']):return False
  if not 0<=now-body['monotonic']<=1.5:return False
  rows=body['targets']
  if type(rows) is not list or any(type(r) is not dict for r in rows):return False
  if len(rows)!=2 or len({tuple(r['fifo']) for r in rows})!=2:return False
  matches=[r for r in rows if r['fifo']==target['fifo'] and r['pid']==target['pid'] and r['ticks']==target['ticks'] and r['role']==target['role']]
  if len(matches)!=1:return False
  row=matches[0]
  if type(row['pid']) is not int or type(row['ticks']) is not int or type(row['fifo']) is not list or any(type(v) is not int for v in row['fifo']):return False
  if type(row['monotonic']) not in (int,float) or not math.isfinite(row['monotonic']) or type(row['errors']) is not list:return False
  if not 0<=now-row['monotonic']<=1.5 or row['errors'] or type(row['state']) is not str or row['state'] not in ('R','S','D','T','t','K','W','P','I'):return False
  writers=row['writers']
  return type(writers) is list and bool(writers) and len(writers)<=16 and all(type(w) is dict and type(w['fd']) is int and w['fd']>=0 and type(w['mode']) is int and w['mode'] in (1,2) for w in writers)
 except (KeyError,ValueError,TypeError):return False
