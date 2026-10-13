"""Existing authorized server only: private native POV diagnostic, real PC env."""
import os,subprocess
from pathlib import Path
base=Path('/workspace/sub01-home-private');project=base/'project/Sub01HomeLab'
env=os.environ.copy();env['SUB01_ADMIN_TOKEN']=(base/'pc-bridge/operator-token').read_text().strip()
image=base/'evidence/native/native-desk-hands-pc.png';image.parent.mkdir(parents=True,exist_ok=True)
args=['runuser','-u','unreal','--','timeout','180','/workspace/sub01-unreal/UE/Engine/Binaries/Linux/UnrealEditor-Cmd',str(project/'Sub01HomeLab.uproject'),'/Game/Sub01Home/ActualHome','-game','-RenderOffscreen','-vulkan','-unattended','-NoSound','-NoSplash','-windowed','-ResX=1280','-ResY=720','-Sub01HandsDiagnostic=DeskTyping','-Sub01DiagnosticSeat','-Sub01DiagnosticMesh=/Game/Sub01Hands/FBX/SUB01_OriginalOwner.SUB01_OriginalOwner','-Sub01DiagnosticClip=/Game/Sub01Hands/FBX/SUB01_DeskTyping.SUB01_DeskTyping','-Sub01CaptureViewport','-Sub01CaptureAfter=45','-Sub01CapturePath='+str(image)]
with (base/'logs/native-desk-hands-pc.log').open('w')as log:
 result=subprocess.run(args,env=env,stdout=log,stderr=subprocess.STDOUT)
if image.is_file():subprocess.run(['runuser','-u','unreal','--','chmod','644',str(image)],check=True)
print('NATIVE_DESK_DIAGNOSTIC_EXIT',result.returncode,'IMAGE_BYTES',image.stat().st_size if image.is_file() else 0)
raise SystemExit(result.returncode)
