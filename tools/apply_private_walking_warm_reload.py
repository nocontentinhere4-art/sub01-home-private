"""Use supported exact console reload commands on the same private Game; reversible."""
from pathlib import Path
import hashlib,json,os,subprocess,time,urllib.request,shutil
PRIVATE=Path('/home/unreal/.sub01-private');P=Path('/workspace/sub01-private-playable-14acd9d355c6/Sub01HomeLab')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def run():
 from private_home_candidate_scope import proc,PLAYABLE_MAP_SHA,PLAYABLE_MODULE_SHA
 from launch_private_persistent_editor import verified_window
 verified_window(Path('/run/sub01-home-private/runtime-window.json'));assert proc(193148)[0]==978377926 and proc(198702)[0]==978621779
 d=json.loads((PRIVATE/'walking-warm-prepare.json').read_text());assert d['game_pid']==193148 and d['game_start_ticks']==978377926 and sha(P/'Config/DefaultGame.ini')==d['config_after_sha256']
 assert sha(P/'Content/Sub01Home/ActualHome.umap')==PLAYABLE_MAP_SHA and sha(P/'Binaries/Linux/libUnrealEditor-Sub01HomeLab.so')==PLAYABLE_MODULE_SHA
 before=json.loads((PRIVATE/'native-visual-metrics.json').read_text());privacy=json.loads((PRIVATE/'native-view-privacy.json').read_text());assert privacy['view_mode']=='manual'and privacy['physical_camera_private']is False and time.time()-privacy['captured_utc']<2
 tv=json.loads((PRIVATE/'native-tv-focus.json').read_text());assert tv.get('focused')is False
 key=(PRIVATE/'operator-token').read_text().strip()
 with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8811/pc/state',headers={'X-Admin-Token':key}),timeout=5)as response:assert json.load(response).get('session')is False
 env={'PATH':'/usr/local/bin:/usr/bin:/bin','DISPLAY':':99','XAUTHORITY':str(PRIVATE/'native-xauthority'),'HOME':'/home/unreal'}
 def xd(*args):return subprocess.run(['/usr/bin/xdotool',*args],env=env,capture_output=True,text=True,check=True).stdout.strip()
 windows=xd('search','--pid','193148','.').split();matches=[]
 for wid in windows:
  if wid.isdigit()and xd('getwindowpid',wid)=='193148'and'Sub01HomeLab'in xd('getwindowname',wid):matches.append(wid)
 assert len(matches)==1,'One actual same-Game native window required'
 window=matches[0];log=Path(json.loads((PRIVATE/'playable-promotion-result.json').read_text())['new_log']);offset=log.stat().st_size
 def tail():
  with log.open('r',errors='replace')as stream:stream.seek(offset);return stream.read()
 def command(text):
  assert text in ['ReloadConfig Sub01HomeCharacter','ReloadPrivateWalkingHands','getall Sub01HomeCharacter HandsMeshPath','getall Sub01HomeHandsInstance TargetSequence','getall SkeletalMeshComponent SkeletalMeshAsset']
  assert proc(193148)[0]==978377926
  xd('windowfocus',window);xd('key','--clearmodifiers','Escape');xd('key','--clearmodifiers','grave');time.sleep(.15);xd('type','--clearmodifiers','--delay','2',text);xd('key','Return');time.sleep(.8);xd('key','Escape')
 try:
  command('ReloadConfig Sub01HomeCharacter');until=time.time()+5
  while time.time()<until and "Branch 'Game' had been unloaded. Reloading on-demand"not in tail():time.sleep(.1)
  assert "Branch 'Game' had been unloaded. Reloading on-demand"in tail(),'Actual engine config cache-unload proof absent'
  command('ReloadPrivateWalkingHands');until=time.time()+60
  while time.time()<until and'SUB01_WALKING_CONFIG_RELOADED'not in tail():time.sleep(.2)
  assert'SUB01_WALKING_CONFIG_RELOADED binding=Walk: verified native skeletal clip bound.'in tail(),tail()[-2500:]
  for cmd in ['getall Sub01HomeCharacter HandsMeshPath','getall Sub01HomeHandsInstance TargetSequence','getall SkeletalMeshComponent SkeletalMeshAsset']:command(cmd)
  text=tail();assert d['new_mesh']in text and d['new_walk']in text,'Actual reflected new mesh AND animation binding required'
  assert proc(193148)[0]==978377926 and proc(198702)[0]==978621779
  time.sleep(.6);after=json.loads((PRIVATE/'native-visual-metrics.json').read_text());assert after['native_pid']==193148 and after['native_start_ticks']==978377926
  old=before['actual_camera_world_cm'];new=after['actual_camera_world_cm'];error=sum((old[k]-new[k])**2 for k in 'xyz')**.5;assert error<=.1,'No player/camera movement permitted during warm binding'
  result={'schema':'sub01.actual-private-walking-warm-binding.v1','game_pid':193148,'game_start_ticks':978377926,'backend_pid':198702,'new_mesh':d['new_mesh'],'new_walk':d['new_walk'],'actual_reflected_mesh_and_target_sequence_verified':True,'camera_displacement_cm':error,'game_pod_devices_restarted':False,'contact_ready':False,'walking_only':True,'old_idle_not_reused':True,'freeze_at_rest_limitation':True,'status':'warm-bound-awaiting-private-walk-QA','log_excerpt':text[-12000:],'epoch':time.time()}
 except Exception as error:
  shutil.copy2(Path(d['backup'])/'DefaultGame.ini',P/'Config/DefaultGame.ini');assert sha(P/'Config/DefaultGame.ini')==d['config_before_sha256'];command('ReloadConfig Sub01HomeCharacter');command('ReloadPrivateWalkingHands');result={'schema':'sub01.actual-private-walking-warm-binding.v1','status':'rolled-back-config-and-old-owner','error':str(error),'game_pid':193148,'game_start_ticks':978377926,'game_restarted':False,'epoch':time.time()}
 (PRIVATE/'walking-warm-binding.json').write_text(json.dumps(result,indent=2)+'\n');(PRIVATE/'walking-warm-binding.json').chmod(0o600);(P/'private-audit/walking-warm-binding.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items()if k!='log_excerpt'}))
if __name__=='__main__':run()
