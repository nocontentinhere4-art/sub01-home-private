"""Freeze a reviewed real candidate into independent playable files, never launch.

Requires a root-owned exact-map approval. The live Game/grants/devices and warm
candidate Editor are read-only throughout. The writable project shares no inode.
"""
import hashlib,json,os,shutil,time
from pathlib import Path
ROOT=Path('/workspace/sub01-private-candidate-20261015/Sub01HomeLab')
PRIVATE=Path('/home/unreal/.sub01-private')
REQUIRED=['reference-wall-console-native.json','reference-teal-bathroom-native.json','reference-bed-finish-native.json','reference-kitchen-grain-native.json','reference-photo-plants-native.json','chosen-bath4000-native.json','chosen-bed-lamp-native.json']
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def run():
 from private_home_candidate_scope import active_candidate_guard,trusted_json,SCOPE,proc
 from launch_private_persistent_editor import verified_window
 verified_window(Path('/run/sub01-home-private/runtime-window.json'))
 from prepare_private_home_candidate import invariants
 # This command is root-launched, so guard identity is independently checked
 # against the sole actual Editor rather than pretending root is that Editor.
 scope=trusted_json(SCOPE);editor=proc(scope['editor_pid']);assert editor[0]==scope['editor_start_ticks']and editor[1]!='Z'
 approval=trusted_json(Path('/run/sub01-home-private/promotion-approved.json'));map_path=ROOT/'Content/Sub01Home/ActualHome.umap';map_sha=sha(map_path)
 assert approval.get('schema')=='sub01.reviewed-private-home-promotion-approval.v1'and approval.get('map_sha256')==map_sha and approval.get('source_project')==str(ROOT)and approval.get('native_saved_assets_and_actual_images_reviewed')is True
 assert approval.get('execute_handoff')is False,'Preparation does not authorize a process handoff'
 def stable_invariants():
  d=invariants();d['game'].pop('state',None);return d
 before=stable_invariants();receipts={}
 build=Path('/workspace/sub01-private-native-build/Sub01HomeLab');build_receipt=json.loads((build/'candidate-motion-lamp-build.json').read_text())
 assert build_receipt.get('status')=='finished'and build_receipt.get('exit')==0 and build_receipt.get('native_compiled')is True and build_receipt.get('original_runtime_unchanged')is True
 assert approval.get('module_sha256')==build_receipt['module_sha256']and sha(build/'Binaries/Linux/libUnrealEditor-Sub01HomeLab.so')==build_receipt['module_sha256']
 assert sha(build/'Source/Sub01HomeLab/Sub01HomeLab.cpp')==build_receipt['source_cpp_sha256']and sha(build/'Source/Sub01HomeLab/Sub01HomeLab.h')==build_receipt['source_header_sha256']
 assert json.loads((build/'Binaries/Linux/UnrealEditor.modules').read_text())['BuildId']=='55116800'
 review_path=Path(approval['reviewed_capture_receipt']);assert review_path.is_relative_to(ROOT/'evidence')and sha(review_path)==approval['reviewed_capture_sha256'];review=json.loads(review_path.read_text());assert review['all_images_complete']and review['candidate_map_sha256']==map_sha and len(review['images'])==8 and all(i['complete_png_verified']for i in review['images'])
 for name in REQUIRED:
  p=ROOT/'private-audit'/name;d=json.loads(p.read_text());assert d.get('saved')is True,name;receipts[name]=sha(p)
 assert receipts==approval.get('required_receipt_sha256'),'Approval must identify every exact actual saved asset receipt'
 for request in(SCOPE.parent/'candidate-requests').glob('*.json'):assert(ROOT/'private-audit'/(request.stem+'-result.json')).is_file(),'Finish every candidate task before freeze'
 target=Path('/workspace')/('sub01-private-playable-'+map_sha[:12])/'Sub01HomeLab';assert not target.exists(),'Never overwrite playable revision';files=[(ROOT/'Sub01HomeLab.uproject',Path('Sub01HomeLab.uproject'))]
 for name in ['Content','SourceAssets','Config']:
  files.extend((p,p.relative_to(ROOT))for p in(ROOT/name).rglob('*')if p.is_file())
 for name in ['Binaries','Source']:
  files.extend((p,p.relative_to(build))for p in(build/name).rglob('*')if p.is_file())
 assert all(not p.is_symlink()for p,relative in files);total=sum(p.stat().st_size for p,relative in files);assert total<4_000_000_000 and len(files)<20000,(total,len(files));assert shutil.disk_usage('/workspace').free>total+1_000_000_000,'Preserve sufficient persistent disk reserve';target.mkdir(parents=True);rows=[]
 for p,relative in files:
  q=target/relative;q.parent.mkdir(parents=True,exist_ok=True);digest=sha(p);shutil.copy2(p,q)
  if digest!=sha(q)or digest!=sha(p)or(p.stat().st_ino,p.stat().st_dev)==(q.stat().st_ino,q.stat().st_dev):raise RuntimeError('Concurrent change or non-independent copy refused')
  rows.append({'path':str(relative),'sha256':digest,'bytes':p.stat().st_size})
 assert sha(map_path)==map_sha and stable_invariants()==before,'Original runtime or reviewed candidate changed during freeze'
 receipt={'schema':'sub01.independent-reviewed-private-playable-revision.v1','source_project':str(ROOT),'playable_project':str(target),'map_sha256':map_sha,'module_sha256':sha(target/'Binaries/Linux/libUnrealEditor-Sub01HomeLab.so'),'owned_module_build_receipt_sha256':sha(build/'candidate-motion-lamp-build.json'),'source_cpp_sha256':build_receipt['source_cpp_sha256'],'source_header_sha256':build_receipt['source_header_sha256'],'independent_writable_copies':True,'all_file_hashes_verified':True,'original_runtime_unchanged':True,'bytes':total,'files':rows,'required_receipts':receipts,'epoch':time.time(),'launched':False}
 audit=target/'private-audit';audit.mkdir();(audit/'playable-copy.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({k:v for k,v in receipt.items()if k!='files'}))
if __name__=='__main__':run()
