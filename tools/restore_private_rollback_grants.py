"""Restore existing private controls only after exact current consumer recovery."""
import ast,hashlib,json,os,time,urllib.request
from pathlib import Path
P=Path('/home/unreal/.sub01-private')
PROJECT=Path('/workspace/sub01-private-playable-next-20261016/Sub01HomeLab')
GAME=(215923,979985246)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def proc(pid,start):
 p=Path('/proc')/str(pid);s=(p/'stat').read_text().rsplit(')',1)[1].split();assert int(s[19])==start and s[0]!='Z';assert int((p/'status').read_text().split('Uid:')[1].split()[0])==1001;return(p/'cmdline').read_bytes().split(b'\0')
def run():
 from launch_private_persistent_editor import verified_window
 verified_window(Path('/run/sub01-home-private/runtime-window.json'))
 assert str(PROJECT/'Sub01HomeLab.uproject').encode()in proc(*GAME)
 for p,h in [('Content/Sub01Home/ActualHome.umap','8af53924a1749df2f023d1428103bbec9fff182a25b9bf3570aa8a33a6c0a6e7'),('Config/DefaultGame.ini','a46b973bc17d64a11743ef5fc04b12e0ee8b0a65feb0a2ec72944964f3fc40eb'),('Binaries/Linux/libUnrealEditor-Sub01HomeLab.so','e571937b708c8e860d05373f1d3de428bc22a4c547cf80ded1ef80db706ace96')]:assert sha(PROJECT/p)==h
 d=json.loads((P/'exact-rollback-policy-recovery.log').read_text().splitlines()[-1]);r=d['rollout'];assert r['status']=='backend-refreshed-awaiting-root-manual-QA'and r['game_identity_unchanged']=={'pid':GAME[0],'start_ticks':GAME[1]}and r['service_environment_restored_exact']
 source=Path('/home/unreal/sub01-backend/home_minecraft_input.py');assert sha(source)==r['policy_after_sha256'];wanted={'PROJECT':str(PROJECT/'Sub01HomeLab.uproject'),'NATIVE_PID':GAME[0],'NATIVE_START_TICKS':GAME[1]};got={}
 for n in ast.parse(source.read_text()).body:
  if isinstance(n,ast.Assign):
   for t in n.targets:
    if isinstance(t,ast.Name)and t.id in wanted:assert t.id not in got;got[t.id]=ast.literal_eval(n.value)
 assert got==wanted
 args=proc(r['backend_pid'],r['backend_start_ticks']);assert b'live_server.py'in args and b'8820'in args
 for pid,start in [(62755,975065256),(62757,975065274)]:proc(pid,start)
 def fresh():
  privacy=json.loads((P/'native-view-privacy.json').read_text());metrics=json.loads((P/'native-visual-metrics.json').read_text())
  for v in [privacy,metrics]:assert(v['native_pid'],v['native_start_ticks'])==GAME and 0<=time.time()-v['captured_utc']<2
  assert privacy['physical_camera_private']is False and privacy['view_mode']=='manual';return metrics
 before=fresh();key=(P/'operator-token').read_text().strip();request=urllib.request.Request('http://127.0.0.1:8820/api/home/native_command',headers={'X-Admin-Token':key})
 with urllib.request.urlopen(request,timeout=5)as response:assert json.load(response).get('privacy')is False
 assert fresh()['actual_camera_world_cm']==before['actual_camera_world_cm']
 for name in ['native-viewer-capture-enabled','native-viewer-input-enabled']:
  value={'native_pid':GAME[0],'native_start_ticks':GAME[1],'purpose':'owner-authorized-private-playable-QA','accepted_game_pixels':True}
  if name.endswith('input-enabled'):value['view_mode']='manual'
  path=P/name;temp=path.with_suffix('.recovery.tmp');temp.write_text(json.dumps(value));os.chown(temp,1001,1001);temp.chmod(0o600);os.replace(temp,path)
 result={'schema':'sub01.private-rollback-session-recovered.v1','game_pid':GAME[0],'game_start_ticks':GAME[1],'project':str(PROJECT),'backend_pid':r['backend_pid'],'backend_start_ticks':r['backend_start_ticks'],'consumer_exact':True,'grants_restored':True,'camera_at_restore':before['actual_camera_world_cm'],'prior_upstairs_pose_preserved':False,'kitchen_three_fix_revision_live':False,'PC_VM_preserved':True,'no_renderer_or_pod_restart_by_recovery':True,'epoch':time.time()}
 (P/'rollback-recovery-result.json').write_text(json.dumps(result,indent=2)+'\n');return result
if __name__=='__main__':print(json.dumps(run()))
