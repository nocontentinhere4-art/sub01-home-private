"""Private existing-server only: real GameViewport of opt-in measured arm contact."""
import argparse,os,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--phase',type=float,choices=[4.,6.,7.],required=True);a=p.parse_args()
base=Path('/workspace/sub01-home-private');project=base/'project/Sub01HomeLab';phase=str(int(a.phase))
env=os.environ.copy();env['SUB01_ADMIN_TOKEN']=(base/'pc-bridge/operator-token').read_text().strip()
image=base/f'evidence/native/native-contact-phase-{phase}.png';image.parent.mkdir(parents=True,exist_ok=True)
if image.exists():subprocess.run(['runuser','-u','unreal','--','rm',str(image)],check=True)
args=['runuser','-u','unreal','--','timeout','300','/workspace/sub01-unreal/UE/Engine/Binaries/Linux/UnrealEditor-Cmd',str(project/'Sub01HomeLab.uproject'),'/Game/Sub01Home/ActualHome','-game','-RenderOffscreen','-vulkan','-unattended','-NoSound','-NoSplash','-windowed','-ResX=1280','-ResY=720','-Sub01HandsDiagnostic=DeskTyping','-Sub01DiagnosticSeat','-Sub01DiagnosticMesh=/Game/Sub01Hands/FBX/SUB01_OriginalOwner.SUB01_OriginalOwner','-Sub01DiagnosticClip=/Game/Sub01Hands/FBX/SUB01_DeskTyping.SUB01_DeskTyping','-Sub01ContactProfile='+str(project/'unreal-skinned-contact-audit.json'),'-Sub01ContactFreeze='+str(a.phase),'-Sub01CaptureViewport','-Sub01CaptureAfter=45','-Sub01CapturePath='+str(image)]
with (base/f'logs/native-contact-phase-{phase}.log').open('w')as log:r=subprocess.run(args,env=env,stdout=log,stderr=subprocess.STDOUT)
if image.is_file():subprocess.run(['runuser','-u','unreal','--','chmod','644',str(image)],check=True)
print('NATIVE_CONTACT_DIAGNOSTIC_EXIT',r.returncode,'PHASE',a.phase,'IMAGE_BYTES',image.stat().st_size if image.is_file() else 0)
raise SystemExit(r.returncode)
