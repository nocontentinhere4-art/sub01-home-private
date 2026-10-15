"""Seal candidate scenery into the verified live-runtime baseline, without launch.

Only the renderer owner executes this on Runpod as unreal. A root-owned exact
map approval supplies reviewed captures and the validated compatible Idle clip.
The live Game, grants, device processes and candidate Editor are read-only.
"""
from pathlib import Path
import concurrent.futures, hashlib, json, os, re, shutil, time

CANDIDATE=Path('/workspace/sub01-private-candidate-20261015/Sub01HomeLab')
OLD=Path('/workspace/sub01-private-playable-next-20261016/Sub01HomeLab')
TARGET=Path('/workspace/sub01-private-playable-kitchen-r1-20261016/Sub01HomeLab')
MODULE='e571937b708c8e860d05373f1d3de428bc22a4c547cf80ded1ef80db706ace96'
CONFIG='a46b973bc17d64a11743ef5fc04b12e0ee8b0a65feb0a2ec72944964f3fc40eb'

def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb')as stream:
  while block:=stream.read(2**20):h.update(block)
 return h.hexdigest()

def run():
 from private_home_candidate_scope import trusted_json,proc,SCOPE
 from unreal_editor_task_queue import guard_valid
 assert os.getuid()==1001 and guard_valid(now=time.time()+600)
 approval=trusted_json('/run/sub01-home-private/promotion-approved.json')
 assert approval['schema']=='sub01.reviewed-private-home-promotion-approval.v1'
 assert approval['execute_handoff']is False and approval['source_project']==str(CANDIDATE)
 assert approval['native_saved_assets_and_actual_images_reviewed']is True
 assert approval['source_e571_and_approved_live_hands_preserved']is True
 baseline=json.loads((TARGET/'baseline-copy.json').read_text())
 assert baseline['all_source_copy_hashes_verified']and baseline['no_hardlinks']
 assert baseline['target_project']==str(TARGET)and baseline['old_project']==str(OLD)
 assert not (TARGET/'private-audit/playable-copy.json').exists(),'Never reseal an accepted revision'
 def live_unchanged():
  identity=proc(209503)
  assert identity[0]==979714171 and identity[1]!='Z'and str(OLD/'Sub01HomeLab.uproject').encode()in identity[2]
  assert sha(OLD/'Binaries/Linux/libUnrealEditor-Sub01HomeLab.so')==MODULE
  assert sha(OLD/'Config/DefaultGame.ini')==CONFIG
  scope=trusted_json(SCOPE);editor=proc(scope['editor_pid'])
  assert editor[0]==scope['editor_start_ticks']and editor[1]!='Z'and str(CANDIDATE/'Sub01HomeLab.uproject').encode()in editor[2]
 live_unchanged()
 map_path=CANDIDATE/'Content/Sub01Home/ActualHome.umap'
 assert sha(map_path)==approval['map_sha256']and approval['module_sha256']==MODULE
 captures=approval['reviewed_actual_captures'];assert captures
 for row in captures:
  path=Path(row['path']).resolve();assert path.is_relative_to(CANDIDATE/'evidence')
  assert sha(path)==row['sha256']and path.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
 config=(OLD/'Config/DefaultGame.ini').read_text()
 protected=set(approval.get('additional_preserved_asset_paths',[]))
 for prefix in approval.get('additional_preserved_asset_prefixes',[]):
  assert prefix.startswith('Content/')and '..'not in Path(prefix).parts
  protected.update(str(p.relative_to(OLD))for p in (OLD/prefix).rglob('*')if p.is_file())
 for asset in re.findall(r'/Game/[A-Za-z0-9_/]+',config):
  protected.add('Content/'+asset.removeprefix('/Game/')+'.uasset')
 for relative in protected:
  assert relative.startswith('Content/')and '..'not in Path(relative).parts
  old=OLD/relative
  if old.is_file():assert sha(TARGET/relative)==sha(old)
 # Existing accepted Idle/Walk/config are retained byte-for-byte.
 assert sha(TARGET/'Config/DefaultGame.ini')==CONFIG
 files=[];skipped=[];overwritten=[]
 for name in ('Content','SourceAssets'):
  for source in (CANDIDATE/name).rglob('*'):
   if not source.is_file():continue
   assert not source.is_symlink();relative=str(source.relative_to(CANDIDATE))
   if relative in protected:
    skipped.append(relative);continue
   if (TARGET/relative).exists()and sha(TARGET/relative)!=sha(source):overwritten.append(relative)
   files.append((source,relative))
 total=sum(p.stat().st_size for p,_ in files)
 assert total<8_000_000_000 and shutil.disk_usage(TARGET).free>total+1_000_000_000
 def copy(row):
  source,relative=row;out=TARGET/relative;digest=sha(source)
  out.parent.mkdir(parents=True,exist_ok=True)
  if not out.exists()or sha(out)!=digest:shutil.copy2(source,out)
  assert sha(out)==digest==sha(source)
  assert (source.stat().st_dev,source.stat().st_ino)!=(out.stat().st_dev,out.stat().st_ino)
 with concurrent.futures.ThreadPoolExecutor(max_workers=4)as pool:list(pool.map(copy,files))
 assert sha(TARGET/'Config/DefaultGame.ini')==CONFIG
 live_unchanged();assert sha(map_path)==approval['map_sha256']
 for relative in protected:
  if (OLD/relative).is_file():assert sha(TARGET/relative)==sha(OLD/relative)
 # The complete original live executable/source/config baseline is retained,
 # with DefaultGame.ini the sole explicitly reviewed config change.
 for row in baseline['files']:
  if row['path'].startswith(('Binaries/','Source/','Config/'))and row['path']!='Config/DefaultGame.ini':assert sha(TARGET/row['path'])==row['sha256']
 rows=[]
 for name in ('Content','SourceAssets','Config','Binaries','Source'):
  for p in sorted((TARGET/name).rglob('*')):
   if p.is_file():
    assert not p.is_symlink()
    rows.append({'path':str(p.relative_to(TARGET)),'bytes':p.stat().st_size,'sha256':sha(p)})
 p=TARGET/'Sub01HomeLab.uproject';rows.append({'path':p.name,'bytes':p.stat().st_size,'sha256':sha(p)})
 assert sha(TARGET/'Content/Sub01Home/ActualHome.umap')==approval['map_sha256']
 result={'schema':'sub01.independent-reviewed-private-playable-revision.v1','source_project':str(CANDIDATE),'playable_project':str(TARGET),'map_sha256':approval['map_sha256'],'module_sha256':MODULE,'config_sha256':sha(TARGET/'Config/DefaultGame.ini'),'independent_writable_copies':True,'all_file_hashes_verified':True,'original_runtime_unchanged':True,'protected_live_assets':sorted(protected),'candidate_protected_files_skipped':skipped,'candidate_existing_files_updated':overwritten,'existing_validated_idle_and_config_preserved':True,'files':rows,'bytes':sum(r['bytes']for r in rows),'epoch':time.time(),'launched':False}
 audit=TARGET/'private-audit';audit.mkdir(exist_ok=True)
 (audit/'playable-copy.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({k:v for k,v in result.items()if k not in ('files',)}),flush=True)

if __name__=='__main__':run()
