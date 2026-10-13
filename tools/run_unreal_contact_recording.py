"""Actual native viewport recording, original bimanual onepass; existing pod only."""
import json,os,subprocess,uuid,time
from pathlib import Path
base=Path('/workspace/sub01-home-private');project=base/'project/Sub01HomeLab';folder=base/('evidence/native/contact-onepass-'+uuid.uuid4().hex)
folder.mkdir(parents=True,exist_ok=True);folder.chmod(0o777)
env=os.environ.copy();env['SUB01_ADMIN_TOKEN']=Path('/home/unreal/.sub01-private/operator-token').read_text().strip()
env['SUB01_PC_ORIGIN']=os.environ.get('SUB01_PC_ORIGIN','http://127.0.0.1:8811')
env['SUB01_HOME_ORIGIN']='http://127.0.0.1:8821'
args=['runuser','-u','unreal','--','timeout','900','/workspace/sub01-unreal/UE/Engine/Binaries/Linux/UnrealEditor-Cmd',str(project/'Sub01HomeLab.uproject'),'/Game/Sub01Home/ActualHome','-game','-RenderOffscreen','-vulkan','-unattended','-NoSound','-NoSplash','-windowed','-ResX=1280','-ResY=720','-ExecCmds=t.MaxFPS 60,t.IdleWhenNotForeground 0,r.VSync 0,Slate.bAllowThrottling 0','-Sub01HandsDiagnostic=DeskTyping','-Sub01DiagnosticSeat','-Sub01RecordKeepAlive','-Sub01LiveHome','-Sub01NativeControl=/home/unreal/.sub01-private/native-control.json','-Sub01DiagnosticMesh=/Game/Sub01Hands/FBX/SUB01_OriginalOwner.SUB01_OriginalOwner','-Sub01DiagnosticClip=/Game/Sub01Hands/FBX/SUB01_DeskTyping.SUB01_DeskTyping','-Sub01ContactProfile='+str(project/'unreal-skinned-contact-audit.json'),'-Sub01ContactRecordDir='+str(folder)]
with (base/'logs/native-contact-onepass.log').open('w')as log:
 process=subprocess.Popen(args,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
 end=time.monotonic()+900
 while not (folder/'frames.json').is_file():
  if process.poll()is not None:raise SystemExit(process.returncode or 'Native runtime ended before frames')
  if time.monotonic()>end:process.terminate();raise SystemExit('Native recording deadline')
  time.sleep(2)
 print('ACTUAL_NATIVE_RUNTIME_KEPT_ALIVE_PID',process.pid,flush=True)
subprocess.run(['runuser','-u','unreal','--','chmod','-R','a+rX',str(folder)],check=True)
data=json.loads((folder/'frames.json').read_text());frames=data['frames']
assert len(frames)>3
assert all((folder/f['file']).is_file()for f in frames)
assert all(frames[i+1]['wallSeconds']>frames[i]['wallSeconds']for i in range(len(frames)-1))
data['timingNote']='evaluatedClipSeconds is last evaluated pose BEFORE viewport request, not exact exposure timestamp'
data['runFolder']=folder.name
(folder/'recording-evidence.json').write_text(json.dumps(data,indent=2))
lines=[]
for i,frame in enumerate(frames):
 lines.append('file '+frame['file'])
 if i+1<len(frames):lines.append('duration '+str(frames[i+1]['wallSeconds']-frame['wallSeconds']))
lines.append('file '+frames[-1]['file']);(folder/'frames.ffconcat').write_text('\n'.join(lines)+'\n')
output=base/'evidence/native/native-contact-onepass.mp4'
if output.exists():output.unlink()
subprocess.run(['ffmpeg','-y','-loglevel','error','-f','concat','-safe','0','-i',str(folder/'frames.ffconcat'),'-fps_mode','vfr','-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart',str(output)],check=True)
print('ACTUAL_CONTACT_VIEWPORT_FRAMES',len(frames),'REAL_WALL_SECONDS',frames[-1]['wallSeconds']-frames[0]['wallSeconds'],'MP4_BYTES',output.stat().st_size)
