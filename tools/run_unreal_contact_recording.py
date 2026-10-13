"""Actual native viewport recording, original bimanual onepass; existing pod only."""
import json,os,subprocess
from pathlib import Path
base=Path('/workspace/sub01-home-private');project=base/'project/Sub01HomeLab';folder=base/'evidence/native/contact-onepass'
folder.mkdir(parents=True,exist_ok=True);folder.chmod(0o777)
env=os.environ.copy();env['SUB01_ADMIN_TOKEN']=(base/'pc-bridge/operator-token').read_text().strip()
args=['runuser','-u','unreal','--','timeout','300','/workspace/sub01-unreal/UE/Engine/Binaries/Linux/UnrealEditor-Cmd',str(project/'Sub01HomeLab.uproject'),'/Game/Sub01Home/ActualHome','-game','-RenderOffscreen','-vulkan','-unattended','-NoSound','-NoSplash','-windowed','-ResX=1280','-ResY=720','-Sub01HandsDiagnostic=DeskTyping','-Sub01DiagnosticSeat','-Sub01DiagnosticMesh=/Game/Sub01Hands/FBX/SUB01_OriginalOwner.SUB01_OriginalOwner','-Sub01DiagnosticClip=/Game/Sub01Hands/FBX/SUB01_DeskTyping.SUB01_DeskTyping','-Sub01ContactProfile='+str(project/'unreal-skinned-contact-audit.json'),'-Sub01ContactRecordDir='+str(folder)]
with (base/'logs/native-contact-onepass.log').open('w')as log:r=subprocess.run(args,env=env,stdout=log,stderr=subprocess.STDOUT)
if r.returncode:raise SystemExit(r.returncode)
subprocess.run(['runuser','-u','unreal','--','chmod','-R','a+rX',str(folder)],check=True)
data=json.loads((folder/'frames.json').read_text());frames=data['frames']
assert len(frames)>3
lines=[]
for i,frame in enumerate(frames):
 lines.append('file '+frame['file'])
 if i+1<len(frames):lines.append('duration '+str(frames[i+1]['wallSeconds']-frame['wallSeconds']))
lines.append('file '+frames[-1]['file']);(folder/'frames.ffconcat').write_text('\n'.join(lines)+'\n')
output=base/'evidence/native/native-contact-onepass.mp4'
subprocess.run(['ffmpeg','-y','-loglevel','error','-f','concat','-safe','0','-i',str(folder/'frames.ffconcat'),'-fps_mode','vfr','-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart',str(output)],check=True)
print('ACTUAL_CONTACT_VIEWPORT_FRAMES',len(frames),'REAL_WALL_SECONDS',frames[-1]['wallSeconds']-frames[0]['wallSeconds'],'MP4_BYTES',output.stat().st_size)
