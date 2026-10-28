#!/usr/bin/env python3
"""Ordinary private stack launcher. Offline candidate; coordinator runs after step2 decision.
No FD census, barrier, subreaper, shim, broad kill, or game lifetime deadline.
"""
import argparse,hashlib,json,os,pwd,secrets,shlex,shutil,socket,subprocess,time
from pathlib import Path
P=Path('/home/unreal/.sub01-private');PD=P/'streamer';SOURCE=Path('/home/sub01-recovery-stage-20261026/runtime-source')
IMPORTED=Path('/home/sub01-animation-reconstruction-20261026-attempt02/case-01/Sub01HomeLab')
ENGINE='/workspace/sub01-private-recovered-engine/Engine/Binaries/Linux/UnrealEditor-Cmd'
PYTHON='/home/unreal/venv/bin/python';VOICE='/home/unreal/voice-rt-venv/bin/python';CHROME='/opt/google/chrome/chrome'
TUNE_SHA='561656b00848a851fd75bd3ee34e9f7823527c12e1c70ec992b958e30341337a'
def need(v,msg):
 if not v:raise RuntimeError(msg)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def ticks(pid):return int(Path('/proc',str(pid),'stat').read_text().rsplit(')',1)[1].split()[19])
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--launch',action='store_true');ap.add_argument('--run-name',required=True);ap.add_argument('--source',default=str(SOURCE));a=ap.parse_args()
 need(a.run_name.replace('-','').isalnum(),'simple unique run-name required');out=P/a.run_name;source=Path(a.source)
 if not a.launch:print(json.dumps({'status':'PLAN_ONLY','out':str(out),'source':str(source),'native_project':'fresh copy of '+str(IMPORTED),'required':'step2 decision, live backend8830/bridge8831, installed Chrome, ancestor ordinary access','agent':'STOP held','game_deadline':None}));return
 need(os.geteuid()==0,'coordinator root required');need(not out.exists(),'fresh run directory required')
 for p in (Path(PYTHON),Path(VOICE),Path(CHROME),Path(ENGINE),IMPORTED/'Sub01HomeLab.uproject',P/'operator-token',P/'integrated-cadence61-20261026/voice.json',source/'scripts/streamer_up.py'):need(p.is_file(),'missing prerequisite '+str(p))
 for port in (8830,8831):
  with socket.socket()as s:s.settimeout(.3);need(s.connect_ex(('127.0.0.1',port))==0,'backend/bridge not listening '+str(port))
 for port in (8835,8837,8838,8839,8840):
  with socket.socket()as s:s.settimeout(.3);need(s.connect_ex(('127.0.0.1',port))!=0,'stack port already occupied '+str(port))
 for display in (99,103):need(not Path('/tmp/.X11-unix/X'+str(display)).exists(),'display already occupied '+str(display))
 tune=P/'streamer-visual-face-tuning.json';saved=Path('/workspace/sub01-recovery-20261026/streamer-visual-face-tuning.json')
 need(sha(tune if tune.exists() else saved)==TUNE_SHA,'p5 differs')
 user=pwd.getpwnam('unreal');need(user.pw_uid==user.pw_gid==1001,'runtime user mismatch')
 need(shutil.disk_usage('/home').free>3*1024**3,'less than3GiB free');os.umask(0o077);out.mkdir();os.chown(out,1001,1001)
 for name in ('logs','recordings','hls'):(out/name).mkdir();os.chown(out/name,1001,1001)
 project=out/'project/Sub01HomeLab';shutil.copytree(IMPORTED,project,ignore=shutil.ignore_patterns('Saved','Intermediate','DerivedDataCache'))
 for directory,dirs,files in os.walk(out/'project'):
  os.chown(directory,1001,1001);os.chmod(directory,0o700)
  for name in files:
   copied=Path(directory)/name;os.chown(copied,1001,1001);os.chmod(copied,0o600)
 PD.mkdir(exist_ok=True);os.chown(PD,1001,1001);(PD/'STOP').touch(exist_ok=True);os.chown(PD/'STOP',1001,1001)
 if not tune.exists():shutil.copyfile(saved,tune);os.chown(tune,1001,1001);tune.chmod(0o600)
 vagon=PD/'vagon.json'
 if not vagon.exists():
  vagon.write_text(json.dumps({'schema':'sub01.streamer-vagon.v1','kind':'workstation','url':'https://app.vagon.io/workstation'})+'\n');os.chown(vagon,1001,1001);vagon.chmod(0o600)
 xdg=P/'xdg-runtime';xdg.mkdir(exist_ok=True);xdg.chmod(0o700);os.chown(xdg,1001,1001)
 auth=out/'xauthority';auth.touch(mode=0o600)
 cookie=''.join('add :'+str(d)+' MIT-MAGIC-COOKIE-1 '+secrets.token_hex(16)+'\n'for d in (99,103))
 subprocess.run(['/usr/bin/xauth','-f',str(auth)],input=cookie,text=True,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10);os.chown(auth,1001,1001)
 control=out/'native-control.json';control.write_text('{"revision":0}\n');os.chown(control,1001,1001)
 base=dict(PATH='/usr/local/bin:/usr/bin:/bin',HOME='/home/unreal',USER='unreal',LANG='C.UTF-8',XAUTHORITY=str(auth))
 receipt={'status':'LAUNCHING','started_utc':time.time(),'p5_sha256':TUNE_SHA,'project':str(project),'source':str(source),'children':[],'STOP':True,'game_deadline':None,'notes':'Own direct launch PIDs only; supervisor owns its service children. No visual/FPS acceptance inferred.'}
 def save():
  temp=out/'receipt.tmp';temp.write_text(json.dumps(receipt,indent=2));os.replace(temp,out/'receipt.json')
 def drop():os.setgroups([]);os.setgid(1001);os.setuid(1001)
 def spawn(name,argv,env):
  with (out/'logs'/f'{name}.log').open('ab')as log:
   p=subprocess.Popen(argv,env=env,cwd='/home/unreal',stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,preexec_fn=drop,start_new_session=True,close_fds=True)
  receipt['children'].append({'name':name,'pid':p.pid,'start_ticks':ticks(p.pid),'argv':argv});save();return p
 save()
 try:
  x=spawn('xvfb-game',['/usr/bin/Xvfb',':99','-screen','0','1920x1080x24','-nolisten','tcp','-auth',str(auth)],base)
  for _ in range(100):
   if Path('/tmp/.X11-unix/X99').exists():break
   need(x.poll() is None,'Xvfb exited');time.sleep(.1)
  need(Path('/tmp/.X11-unix/X99').exists(),'X99 startup failed')
  env=dict(base,DISPLAY=':99',SDL_VIDEODRIVER='x11',XDG_RUNTIME_DIR=str(xdg),SUB01_ADMIN_TOKEN=(P/'operator-token').read_text().strip(),SUB01_HOME_ORIGIN='http://127.0.0.1:8831',SUB01_PC_ORIGIN='http://127.0.0.1:8838',LD_LIBRARY_PATH='/workspace/sub01-home-private/claude-12h/libs/usr/lib/x86_64-linux-gnu',OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='1')
  game=spawn('native',[ENGINE,str(project/'Sub01HomeLab.uproject'),'/Game/Sub01Home/ActualHome','-game','-Sub01CompletionSandbox','-Sub01ManualView','-Sub01StreamerVisual','-Sub01NativeControl='+str(control),'-vulkan','-unattended','-NoSound','-NoSplash','-NoLiveCoding','-NoHotReloadFromIDE','-corelimit=6','-RenderOffScreen','-windowed','-NoBorder','-ResX=1920','-ResY=1080','-ForceRes','-ExecCmds=t.MaxFPS 60,t.IdleWhenNotForeground 0,r.VSync 0,Slate.bAllowThrottling 0','-stdout','-FullStdOutLogOutput'],env)
  gamepid=out/'game.pid';gamepid.write_text(str(game.pid)+'\n');os.chown(gamepid,1001,1001)
  canonical_pid=PD/'game.pid'
  if canonical_pid.exists():shutil.copyfile(canonical_pid,out/'previous-game.pid')
  pidtmp=PD/('.game.pid-'+str(os.getpid()));pidtmp.write_text(str(game.pid)+'\n');os.chown(pidtmp,1001,1001);os.replace(pidtmp,canonical_pid)
  receipt['game_pid_files']=[str(gamepid),str(canonical_pid)];save()
  cmd=[PYTHON,str(source/'scripts/streamer_up.py'),'start','--source',str(source),'--streamer-dir',str(PD),'--token-file',str(P/'operator-token'),'--display',':103','--game-display',':99.0','--desktop-port','8838','--backend-port','8830','--hf-home','/home/sub01-recovery-stage-20261026/voice-public','--voice-config',str(P/'integrated-cadence61-20261026/voice.json'),'--library-path','/usr/local/cuda/lib64','--hls-dir',str(out/'hls'),'--foreground']
  for name in ('desktop','agent','director','monitor','hls'):cmd+=['--'+name+'-python',PYTHON]
  cmd+=['--voice-python',VOICE]
  extras={'xvfb':['-auth',str(auth)],'desktop':['--data-dir',str(PD/'desktop-vagon'),'--pc-mode','vagon','--vagon-kind','workstation','--chromium',CHROME],'voice':['--offline','--fallback','none','--threads','4','--keep-hours','0'],'director':['--game-source','fifo','--game-pid-file',str(gamepid),'--fps','60','--desktop-fps','60','--encoder','libx264','--layout','webcam_only','--recordings-dir',str(out/'recordings'),'--hls-dir',str(out/'hls'),'--min-free-gb','3','--keep-segments','18']}
  for name,argv in extras.items():cmd+=['--child-arg',name+'='+shlex.join(argv)]
  for name in ('director','desktop','monitor'):cmd+=['--child-env',name+'=XAUTHORITY='+str(auth)]
  for key in ('HF_HUB_OFFLINE','TRANSFORMERS_OFFLINE'):cmd+=['--child-env','voice='+key+'=1']
  spawn('stack-supervisor',cmd,base)
  spawn('watchdog',[PYTHON,str(source/'scripts/streamer_watchdog.py'),'--streamer-dir',str(PD),'--token-file',str(P/'operator-token'),'--agent-url','http://127.0.0.1:8836','--desktop-url','http://127.0.0.1:8838','--desktop-data-dir',str(PD/'desktop-vagon')],base)
  receipt['status']='LAUNCHED_NOT_YET_READY';save();print(json.dumps({'receipt':str(out/'receipt.json'),'logs':str(out/'logs'),'native_pid':game.pid,'STOP':True}))
 except BaseException as e:
  receipt['status']='PARTIAL_LAUNCH_REQUIRES_COORDINATOR';receipt['error']=repr(e);save();raise
if __name__=='__main__':main()
