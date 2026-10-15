"""Authorize only an independently copied next-home Editor beside the live Game.

The active-home guard remains mandatory outside the exact isolated project.
Root-owned scope pins the actual original Game and candidate Editor identities.
"""
import hashlib,json,os,stat,time
from pathlib import Path
SOURCE=Path('/workspace/sub01-private-recovered-project/Sub01HomeLab')
CANDIDATE=Path('/workspace/sub01-private-candidate-20261015/Sub01HomeLab')
SCOPE=Path('/run/sub01-home-private/candidate-scope.json')
MAP_SHA='f2072833e5c21aeed43b4aefc63361a45396a3038e0234227dad9bd1501f7617'
MODULE_SHA='97c3395e01e03c2df5f549c7920df289fa69a1073bee71c0b9a93fbfe8f5506a'
HOME_SHA='9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def trusted_json(path):
 path=Path(path);parent=path.parent.lstat();assert stat.S_ISDIR(parent.st_mode)and parent.st_uid==0 and not parent.st_mode&0o022
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
 try:
  st=os.fstat(fd);assert stat.S_ISREG(st.st_mode)and st.st_uid==0 and st.st_nlink==1 and not st.st_mode&0o022;raw=os.read(fd,16385);assert len(raw)<=16384
 finally:os.close(fd)
 return json.loads(raw)
def proc(pid):
 p=Path('/proc')/str(pid);f=(p/'stat').read_text().rsplit(')',1)[1].split();return int(f[19]),f[0],(p/'cmdline').read_bytes().split(b'\0')
def validate_scope(scope,project,game,editor,now):
 assert Path(project).resolve()==CANDIDATE,'Candidate scope cannot authorize the original project'
 assert scope.get('schema')=='sub01.private-next-home-candidate-scope.v1'and scope.get('candidate_project')==str(CANDIDATE)and scope.get('source_project')==str(SOURCE)
 assert scope.get('original_map_sha256')==MAP_SHA and scope.get('module_sha256')==MODULE_SHA
 assert now < scope.get('deadline_epoch',0)<=1792117175 and scope.get('no_live_promotion')is True
 assert scope.get('game_pid')==159171 and scope.get('game_start_ticks')==976840968 and game[0]==976840968 and game[1]!='Z'
 assert str(SOURCE/'Sub01HomeLab.uproject').encode()in game[2]and b'-game'in game[2]
 assert editor[0]==scope.get('editor_start_ticks')and editor[1]!='Z'and str(CANDIDATE/'Sub01HomeLab.uproject').encode()in editor[2]and b'-game'not in editor[2]
 assert scope.get('editor_pid')==os.getpid(),'Scope belongs to one actual candidate Editor process'
 return True
def active_candidate_guard(project=None):
 if project is None:
  try:import unreal;project=unreal.Paths.project_dir()
  except ImportError:return False
 if Path(project).resolve()!=CANDIDATE:return False
 from unreal_editor_task_queue import guard_valid
 assert guard_valid(now=time.time()+60),'Authenticated private GPU window required'
 scope=trusted_json(SCOPE);validate_scope(scope,project,proc(159171),proc(os.getpid()),time.time())
 assert sha(SOURCE/'Content/Sub01Home/ActualHome.umap')==MAP_SHA and sha(SOURCE/'Binaries/Linux/libUnrealEditor-Sub01HomeLab.so')==MODULE_SHA,'Live home map/module must remain unchanged'
 assert sha(CANDIDATE/'private-audit/candidate-copy.json')==scope['copy_receipt_sha256']
 copy=json.loads((CANDIDATE/'private-audit/candidate-copy.json').read_text());assert copy['all_writable_project_files_are_independent_copies']and copy['all_copied_file_hashes_verified']
 assert sha(CANDIDATE/'SourceAssets/full-home.glb')==HOME_SHA and sha(CANDIDATE/'Binaries/Linux/libUnrealEditor-Sub01HomeLab.so')==MODULE_SHA
 return True
def require_project(project):
 path=Path(project).resolve()
 if path==CANDIDATE:assert active_candidate_guard(path);return
 assert path==SOURCE,'Only exact active home or authenticated isolated next-home project allowed'
