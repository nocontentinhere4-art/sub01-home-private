"""Copy the real private home into an isolated writable next-version project.

The human's Game, viewer grants, device services and original project are read
only. No hardlinked project assets or shared writable Saved directory are used.
"""
import hashlib,json,os,shutil,stat,time
from pathlib import Path
SOURCE=Path('/workspace/sub01-private-recovered-project/Sub01HomeLab')
CANDIDATE=Path('/workspace/sub01-private-candidate-20261015/Sub01HomeLab')
GAME_PID=159171;GAME_START=976840968
MAP_SHA='f2072833e5c21aeed43b4aefc63361a45396a3038e0234227dad9bd1501f7617'
MODULE_SHA='97c3395e01e03c2df5f549c7920df289fa69a1073bee71c0b9a93fbfe8f5506a'
MAX_BYTES=1_100_000_000

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def game_identity():
 p=Path('/proc')/str(GAME_PID);fields=(p/'stat').read_text().rsplit(')',1)[1].split();assert int(fields[19])==GAME_START and fields[0]!='Z';args=(p/'cmdline').read_bytes().split(b'\0');assert str(SOURCE/'Sub01HomeLab.uproject').encode()in args and b'-game'in args;return {'pid':GAME_PID,'start_ticks':GAME_START,'state':fields[0]}
def invariants():
 game=game_identity();assert sha(SOURCE/'Content/Sub01Home/ActualHome.umap')==MAP_SHA;assert sha(SOURCE/'Binaries/Linux/libUnrealEditor-Sub01HomeLab.so')==MODULE_SHA
 private=Path('/home/unreal/.sub01-private');grants={n:sha(private/n)if(private/n).is_file()else None for n in('native-viewer-capture-enabled','native-viewer-input-enabled')};return {'game':game,'map_sha256':MAP_SHA,'module_sha256':MODULE_SHA,'viewer_grants_sha256':grants}
def run():
 import sys;sys.path.insert(0,'/home/unreal/runtime-tools')
 from unreal_editor_task_queue import guard_valid
 assert guard_valid(now=time.time()+600),'Authenticated bounded root-owned runtime window required'
 window=json.loads(Path('/run/sub01-home-private/runtime-window.json').read_text());assert window['deadline_epoch']==1792117175 and window['minimum_balance_reserve']>=10 and Path('/proc',str(window['root_guard_pid'])).stat().st_uid==0
 before=invariants();assert not CANDIDATE.exists(),'Never overwrite an existing candidate'
 roots=['Content','SourceAssets','Binaries','Config','Source'];files=[SOURCE/'Sub01HomeLab.uproject',SOURCE/'private-original-source-project-sha-receipt.json']
 for root in roots:
  for p in(SOURCE/root).rglob('*'):
   if p.is_file():files.append(p)
 assert all(not p.is_symlink()for p in files),'No external mutable asset aliases';size=sum(p.stat().st_size for p in files);assert size<MAX_BYTES,size
 CANDIDATE.mkdir(parents=True)
 rows=[]
 for p in files:
  relative=p.relative_to(SOURCE);dest=CANDIDATE/relative;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest);assert dest.stat().st_ino!=p.stat().st_ino or dest.stat().st_dev!=p.stat().st_dev;assert sha(p)==sha(dest);rows.append({'path':str(relative),'bytes':p.stat().st_size,'sha256':sha(dest)})
 after=invariants();assert before['viewer_grants_sha256']==after['viewer_grants_sha256'];audit=CANDIDATE/'private-audit';audit.mkdir()
 receipt={'schema':'sub01.private-next-home-candidate-copy.v1','source_project':str(SOURCE),'candidate_project':str(CANDIDATE),'source_game':before['game'],'copied_bytes':size,'file_count':len(files),'all_writable_project_files_are_independent_copies':True,'all_copied_file_hashes_verified':True,'original_map_sha256':MAP_SHA,'module_sha256':MODULE_SHA,'viewer_grants_unchanged':True,'deadline_epoch':window['deadline_epoch'],'files':rows,'source_game_after':after['game'],'prepared_epoch':time.time(),'editor_started':False,'candidate_native_imported':False,'promoted_to_live':False};(audit/'candidate-copy.json').write_text(json.dumps(receipt,indent=2)+'\n');print('PRIVATE_CANDIDATE_COPY_PASS',json.dumps({k:v for k,v in receipt.items()if k!='files'}),flush=True)
if __name__=='__main__':run()
