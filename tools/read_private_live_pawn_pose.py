"""Supported read-only engine console reflection, only unchanged idle owner input."""
import json,time,subprocess,os
from pathlib import Path
P=Path('/home/unreal/.sub01-private')
def run():
 from private_home_candidate_scope import proc
 assert proc(215923)[0]==979985246
 def metrics():return json.loads((P/'native-visual-metrics.json').read_text())
 before=metrics();privacy=json.loads((P/'native-view-privacy.json').read_text());assert privacy['physical_camera_private']is False and privacy['view_mode']=='manual'and time.time()-privacy['captured_utc']<2
 print('METRICSKEYS',list(before))
 health=json.loads(__import__('urllib.request',fromlist=['urlopen']).urlopen('http://127.0.0.1:8892/health').read());time.sleep(2);health2=json.loads(__import__('urllib.request',fromlist=['urlopen']).urlopen('http://127.0.0.1:8892/health').read());assert health.get('acceptedInputs')==health2.get('acceptedInputs'),'Owner input changed; no console'
 assert json.loads((P/'native-tv-focus.json').read_text()).get('focused')is False
 env={'PATH':'/usr/bin:/bin','DISPLAY':':99','XAUTHORITY':str(P/'native-xauthority'),'HOME':'/home/unreal'}
 def xd(*args):return subprocess.run(['/usr/bin/xdotool',*args],env=env,capture_output=True,text=True,check=True).stdout.strip()
 windows=xd('search','--pid','215923','.').split();windows=[x for x in windows if xd('getwindowpid',x)=='215923'and'Sub01HomeLab'in xd('getwindowname',x)];assert len(windows)==1
 log=Path(json.loads((P/'playable-promotion-result.json').read_text())['new_log']);offset=log.stat().st_size
 for command in ['getall PlayerController ControlRotation','getall CapsuleComponent RelativeLocation']:
  xd('windowfocus',windows[0]);xd('key','--clearmodifiers','Escape');xd('key','--clearmodifiers','grave');time.sleep(.15);xd('type','--clearmodifiers','--delay','2',command);xd('key','Return');time.sleep(.6);xd('key','Escape')
 with log.open(errors='replace')as f:f.seek(offset);text=f.read()
 after=metrics();assert after['actual_camera_world_cm']==before['actual_camera_world_cm'];result={'schema':'sub01.actual-private-pawn-pose-readonly.v1','native_pid':215923,'native_start_ticks':979985246,'before':before,'after':after,'reflected_log':text,'camera_unchanged':True,'epoch':time.time()};(P/'next-playable-pawn-pose-readback.json').write_text(json.dumps(result,indent=2)+'\n');print('POSE_LOG',text)
if __name__=='__main__':run()
