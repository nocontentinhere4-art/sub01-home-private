"""Add verified new private owner assets and a reversible walking-only config override."""
from pathlib import Path
import hashlib,json,os,shutil,time,urllib.request
P=Path('/workspace/sub01-private-playable-14acd9d355c6/Sub01HomeLab')
C=Path('/workspace/sub01-private-candidate-20261015/Sub01HomeLab')
PRIVATE=Path('/home/unreal/.sub01-private')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def run():
 from private_home_candidate_scope import proc,PLAYABLE_MAP_SHA,PLAYABLE_MODULE_SHA
 from launch_private_persistent_editor import verified_window
 verified_window(Path('/run/sub01-home-private/runtime-window.json'));assert proc(193148)[0]==978377926 and proc(198702)[0]==978621779
 assert sha(P/'Content/Sub01Home/ActualHome.umap')==PLAYABLE_MAP_SHA and sha(P/'Binaries/Linux/libUnrealEditor-Sub01HomeLab.so')==PLAYABLE_MODULE_SHA
 r=C/'private-audit';a=json.loads((r/'anatomical-owner-fbx-candidate.json').read_text());g=json.loads((r/'anatomical-owner-gltf-candidate.json').read_text());assert a['initial_inventory_passed']and a['source_sha256']=='fd2f3b8e521b99f8c02d142d1b80f9df0fe3d37bd762b2ca587e0408d53c9f0e'
 assert json.loads((r/'anatomical-component-pose-audit.json').read_text())['motion_phase_verified']and json.loads((r/'anatomical-source-material-binding.json').read_text())['core_factors_textures_transforms_two_sided_verified']
 assert json.loads((PRIVATE/'native-view-privacy.json').read_text())['physical_camera_private']is False
 key=(PRIVATE/'operator-token').read_text().strip()
 with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8811/pc/state',headers={'X-Admin-Token':key}),timeout=5)as response:pc=json.load(response)
 assert pc['privacy']is False and pc.get('session')is False,'Release PC focus before console operations'
 tv=json.loads((PRIVATE/'native-tv-focus.json').read_text());assert tv.get('focused')is False,'Release TV focus before console operations'
 config=P/'Config/DefaultGame.ini';copy=json.loads((P/'private-audit/playable-copy.json').read_text());sealed=next(v['sha256']for v in copy['files']if v['path']=='Config/DefaultGame.ini');assert sha(config)==sealed,'Never overwrite other config work'
 for saved in (P/'Saved/Config').rglob('Game.ini'):
  assert not any(k in saved.read_text()for k in ['HandsMeshPath=','WalkClipPath=','IdleClipPath=','ValidatedHandsPostures=']),'Generated config override needs separate exact review'
 backup=PRIVATE/('walking-warm-rollback-'+str(time.time_ns()));backup.mkdir(mode=0o700);shutil.copy2(config,backup/'DefaultGame.ini');(backup/'DefaultGame.ini').chmod(0o600)
 manifests=[]
 for destination in [g['destination'],a['destination']]:
  assert destination.startswith('/Game/Sub01Hands/AnatomicalCandidate/');relative=Path('Content')/destination.removeprefix('/Game/');source=C/relative;target=P/relative;assert source.is_dir()and not target.exists()
  files=[f for f in source.rglob('*')if f.is_file()];assert files and sum(f.stat().st_size for f in files)<=500_000_000
  for f in files:
   assert not f.is_symlink()and f.suffix in('.uasset','.ubulk','.uexp');out=target/f.relative_to(source);out.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,out);assert sha(f)==sha(out)and(f.stat().st_dev,f.stat().st_ino)!=(out.stat().st_dev,out.stat().st_ino);manifests.append({'path':str(out.relative_to(P)),'sha256':sha(out),'bytes':out.stat().st_size})
 raw=config.read_bytes();mesh=a['meshes'][0]['path'];clip=a['clips'][0]['path'];addition=('\n; Private anatomical walking WIP: true Idle remains held; stop freezes captured Walk.\n[/Script/Sub01HomeLab.Sub01HomeCharacter]\nHandsMeshPath='+mesh+'\nWalkClipPath='+clip+'\nIdleClipPath=\n!ValidatedHandsPostures=ClearArray\n+ValidatedHandsPostures=Walk\n').encode();pending=config.with_suffix('.walking-pending');pending.write_bytes(raw+addition);pending.chmod(0o644);os.replace(pending,config)
 report={'schema':'sub01.private-walking-warm-prepare.v1','game_pid':193148,'game_start_ticks':978377926,'backend_pid':198702,'backend_start_ticks':978621779,'backup':str(backup),'config_before_sha256':sealed,'config_after_sha256':sha(config),'new_mesh':mesh,'new_walk':clip,'copied_files':manifests,'copy_bytes':sum(f['bytes']for f in manifests),'idle_cleared':True,'freeze_at_rest_limitation':True,'map_module_unchanged':True,'contact_ready':False,'game_restarted':False,'console_reload_not_yet_invoked':True,'epoch':time.time()};(PRIVATE/'walking-warm-prepare.json').write_text(json.dumps(report,indent=2)+'\n');(PRIVATE/'walking-warm-prepare.json').chmod(0o600);(P/'private-audit/walking-warm-prepare.json').write_text(json.dumps({k:v for k,v in report.items()if k!='backup'},indent=2)+'\n');print('WALKING_WARM_ASSETS_CONFIG_PREPARED',len(manifests),report['copy_bytes'],report['config_after_sha256'])
if __name__=='__main__':run()
