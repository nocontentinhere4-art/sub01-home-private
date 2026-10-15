"""Independent writable runtime baseline; no process, config, grant or live writes."""
from pathlib import Path
import os,json,hashlib,shutil,time,concurrent.futures
OLD=Path('/workspace/sub01-private-playable-14acd9d355c6/Sub01HomeLab')
TARGET=Path('/workspace/sub01-private-playable-next-20261016/Sub01HomeLab')
MODULE='e571937b708c8e860d05373f1d3de428bc22a4c547cf80ded1ef80db706ace96'
MAP='14acd9d355c66741b7ddfd17d34acbdc5f5f75f8fc71f0a708504f06ff0eeb00'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb')as f:
  while b:=f.read(2**20):h.update(b)
 return h.hexdigest()
def run():
 from private_home_candidate_scope import proc
 from unreal_editor_task_queue import guard_valid
 assert guard_valid(now=time.time()+600);assert proc(193148)[0]==978377926 and proc(198702)[0]==978621779
 assert sha(OLD/'Content/Sub01Home/ActualHome.umap')==MAP and sha(OLD/'Binaries/Linux/libUnrealEditor-Sub01HomeLab.so')==MODULE
 cfg=sha(OLD/'Config/DefaultGame.ini');assert cfg=='7d3ee40243d426fdc173300d812e018ebd17c589f37302b908675f6262a8218d'
 assert not TARGET.exists(),'Use recorded baseline; never overwrite staging work';TARGET.mkdir(parents=True);started=time.time();files=[]
 for name in('Content','Config','Binaries','Source','SourceAssets','private-audit'):
  p=OLD/name
  if p.is_dir():files.extend(f for f in p.rglob('*')if f.is_file())
 files.extend(p for p in OLD.iterdir()if p.is_file()and p.suffix=='.uproject');assert files and sum(f.stat().st_size for f in files)<12_000_000_000
 progress=TARGET/'baseline-copy-progress.json'
 def copy(f):
  assert not f.is_symlink();out=TARGET/f.relative_to(OLD);out.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,out);expected=sha(f);assert sha(out)==expected and(f.stat().st_dev,f.stat().st_ino)!=(out.stat().st_dev,out.stat().st_ino);return {'path':str(f.relative_to(OLD)),'bytes':f.stat().st_size,'sha256':expected}
 rows=[]
 with concurrent.futures.ThreadPoolExecutor(max_workers=4)as pool:
  for i,r in enumerate(pool.map(copy,files)):
   rows.append(r)
   if i%32==0:progress.write_text(json.dumps({'copied_files':len(rows),'total_files':len(files),'copied_bytes':sum(r['bytes']for r in rows),'epoch':time.time()}))
 assert proc(193148)[0]==978377926 and proc(198702)[0]==978621779 and sha(OLD/'Config/DefaultGame.ini')==cfg and sha(OLD/'Content/Sub01Home/ActualHome.umap')==MAP and sha(OLD/'Binaries/Linux/libUnrealEditor-Sub01HomeLab.so')==MODULE
 r={'schema':'sub01.next-playable-independent-baseline.v1','status':'baseline-ready-final-candidate-map-assets-pawn-idle-pending','old_project':str(OLD),'target_project':str(TARGET),'game_pid_preserved':193148,'game_start_preserved':978377926,'backend_pid_preserved':198702,'actual_live_module_sha256':MODULE,'actual_anatomical_config_sha256':cfg,'no_hardlinks':True,'all_source_copy_hashes_verified':True,'files':rows,'bytes':sum(v['bytes']for v in rows),'started_epoch':started,'finished_epoch':time.time(),'promoted':False,'processes_or_grants_modified':False};(TARGET/'baseline-copy.json').write_text(json.dumps(r,indent=2)+'\n');progress.unlink();print('NEXT_BASELINE_READY',len(rows),r['bytes'],r['finished_epoch']-started,flush=True)
if __name__=='__main__':run()
