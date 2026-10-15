"""Prepare approved saved scenery files; never seal, launch or touch live inputs."""
from pathlib import Path
import concurrent.futures,hashlib,json,os,re,shutil,time
CANDIDATE=Path('/workspace/sub01-private-candidate-20261015/Sub01HomeLab')
OLD=Path('/workspace/sub01-private-playable-14acd9d355c6/Sub01HomeLab')
TARGET=Path('/workspace/sub01-private-playable-next-20261016/Sub01HomeLab')
PRESERVED='Content/Sub01Hands/AnatomicalCandidate/FBX_V_8027a9849bcf/Attempt_ee925b3f11c64fee8690b28bce56b66f'
MODULE='e571937b708c8e860d05373f1d3de428bc22a4c547cf80ded1ef80db706ace96'
CONFIG='7d3ee40243d426fdc173300d812e018ebd17c589f37302b908675f6262a8218d'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb')as f:
  while chunk:=f.read(2**20):h.update(chunk)
 return h.hexdigest()
def run():
 from private_home_candidate_scope import trusted_json,proc,SCOPE
 from unreal_editor_task_queue import guard_valid
 assert os.getuid()==1001 and guard_valid(now=time.time()+600)
 baseline=json.loads((TARGET/'baseline-copy.json').read_text());assert baseline['all_source_copy_hashes_verified']and baseline['no_hardlinks']
 assert not(TARGET/'private-audit/playable-copy.json').exists(),'Never edit a sealed playable revision'
 def stable():
  p=proc(193148);assert p[0]==978377926 and p[1]!='Z'and str(OLD/'Sub01HomeLab.uproject').encode()in p[2]
  assert sha(OLD/'Binaries/Linux/libUnrealEditor-Sub01HomeLab.so')==MODULE and sha(OLD/'Config/DefaultGame.ini')==CONFIG
  assert sha(TARGET/'Binaries/Linux/libUnrealEditor-Sub01HomeLab.so')==MODULE and sha(TARGET/'Config/DefaultGame.ini')==CONFIG
  scope=trusted_json(SCOPE);e=proc(scope['editor_pid']);assert e[0]==scope['editor_start_ticks']and e[1]!='Z'and str(CANDIDATE/'Sub01HomeLab.uproject').encode()in e[2]
 stable();mapsha=sha(CANDIDATE/'Content/Sub01Home/ActualHome.umap');protected={str(p.relative_to(OLD))for p in(OLD/PRESERVED).rglob('*')if p.is_file()}
 for asset in re.findall(r'/Game/[A-Za-z0-9_/]+',(OLD/'Config/DefaultGame.ini').read_text()):protected.add('Content/'+asset[6:]+'.uasset')
 for path in protected:
  if(OLD/path).is_file():assert sha(TARGET/path)==sha(OLD/path)
 files=[]
 for name in ('Content','SourceAssets'):
  for p in(CANDIDATE/name).rglob('*'):
   if p.is_file():
    assert not p.is_symlink();relative=str(p.relative_to(CANDIDATE))
    if relative not in protected:files.append((p,relative))
 assert sum(p.stat().st_size for p,_ in files)<8_000_000_000 and shutil.disk_usage(TARGET).free>1_000_000_000
 def sync(row):
  source,relative=row;out=TARGET/relative;digest=sha(source);copied=False
  if not out.exists()or sha(out)!=digest:out.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,out);copied=True
  assert sha(out)==digest==sha(source)and(source.stat().st_dev,source.stat().st_ino)!=(out.stat().st_dev,out.stat().st_ino)
  return {'path':relative,'sha256':digest,'bytes':source.stat().st_size,'copied':copied}
 started=time.time()
 with concurrent.futures.ThreadPoolExecutor(max_workers=4)as pool:rows=list(pool.map(sync,files))
 stable();assert sha(CANDIDATE/'Content/Sub01Home/ActualHome.umap')==mapsha
 for path in protected:
  if(OLD/path).is_file():assert sha(TARGET/path)==sha(OLD/path)
 result={'schema':'sub01.next-private-approved-assets-presynced.v1','map_sha256':mapsha,'files':rows,'protected_live_assets':sorted(protected),'source_e571_module_and_config_preserved':True,'no_hardlinks':True,'all_hashes_verified':True,'game_grants_devices_untouched':True,'sealed':False,'fresh_pose_required_before_seal':True,'started_epoch':started,'finished_epoch':time.time()};(TARGET/'asset-presync.json').write_text(json.dumps(result,indent=2)+'\n');print('APPROVED_ASSETS_PRESYNCED',len(rows),sum(r['bytes']for r in rows if r['copied']),result['finished_epoch']-started,flush=True)
if __name__=='__main__':run()
