"""Record the real authenticated X11 native game window, never a movie camera."""
import argparse,json,os,secrets,subprocess,time,uuid
from pathlib import Path
from unreal_runtime_environment import build_unreal_environment
from unreal_native_display import allocated_a40_bus_id,nvidia_xorg_config,xorg_command,owned_xorg_pid,resize_owned_game_window

BASE=Path('/workspace/sub01-home-private')
PROJECT=BASE/'project/Sub01HomeLab'
PRIVATE=Path('/home/unreal/.sub01-private')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--deadline-epoch',type=int,required=True)
    parser.add_argument('--display-provider',choices=('xvfb','nvidia-xorg'),default='xvfb')
    parser.add_argument('--reuse-display',action='store_true')
    parser.add_argument('--startup-view',choices=('manual','live','desk-diagnostic'),default='manual')
    args=parser.parse_args()
    remaining=args.deadline_epoch-time.time()
    if remaining<90:raise SystemExit('Authorized window too short')
    PRIVATE.mkdir(mode=0o700,parents=True,exist_ok=True)
    os.chown(PRIVATE,1001,1001);PRIVATE.chmod(0o700)
    auth=PRIVATE/'native-xauthority';auth.touch(mode=0o600);os.chown(auth,1001,1001);auth.chmod(0o600)
    if not args.reuse_display:
        cookie=secrets.token_hex(16)
        subprocess.run(['runuser','-u','unreal','--','xauth','-f',str(auth),'source','-'],input=f'add :99 . {cookie}\n',text=True,stdout=subprocess.DEVNULL,check=True)
    env=build_unreal_environment();env.update(DISPLAY=':99',XAUTHORITY=str(auth),SDL_VIDEODRIVER='x11')
    display_env={k:v for k,v in env.items()if not k.startswith('SUB01_')}
    log=BASE/'logs/native-headed-window.log'
    folder=PRIVATE/('window-record-'+uuid.uuid4().hex);folder.mkdir(mode=0o700);os.chown(folder,1001,1001)
    xlog=(BASE/'logs/native-display.log').open('w')
    xvfb=None
    if args.reuse_display:
        if args.display_provider!='nvidia-xorg':raise SystemExit('Reuse requires owned NVIDIA Xorg')
        print('OWNED_AUTHENTICATED_XORG_REUSED_PID',owned_xorg_pid(PRIVATE/'native-xorg.conf',auth),flush=True)
        display=None
    elif args.display_provider=='nvidia-xorg':
        result=subprocess.run(['nvidia-smi','--query-gpu=name,pci.bus_id','--format=csv,noheader'],capture_output=True,text=True,check=True,timeout=10,env=display_env)
        bus_id=allocated_a40_bus_id(result.stdout)
        config=PRIVATE/'native-xorg.conf';config.write_text(nvidia_xorg_config(bus_id));config.chmod(0o600)
        display=['timeout','--kill-after=5',str(int(remaining)),*xorg_command(config,auth,BASE/'logs/native-xorg.log')]
    else:
        display=['runuser','-u','unreal','--','timeout',str(int(remaining)),'Xvfb',':99','-nolisten','tcp','-screen','0','1280x720x24','-auth',str(auth)]
    if display:
        xvfb=subprocess.Popen(display,env=display_env,stdout=xlog,stderr=subprocess.STDOUT)
        time.sleep(2)
        if xvfb.poll()is not None:raise SystemExit('Private native display failed')
    control=PRIVATE/'native-control.json'
    control.write_text(json.dumps({'revision':100}));os.chown(control,1001,1001);control.chmod(0o600)
    native=['runuser','-u','unreal','--','timeout','--kill-after=5',str(max(1,int(args.deadline_epoch-time.time()))),'/workspace/sub01-unreal/UE/Engine/Binaries/Linux/UnrealEditor-Cmd',str(PROJECT/'Sub01HomeLab.uproject'),'/Game/Sub01Home/ActualHome','-game','-vulkan','-corelimit=8','-ZenDataPath=/workspace/sub01-unreal/cache/zen','-unattended','-NoSound','-NoSplash','-windowed','-NoBorder','-WinX=0','-WinY=0','-ResX=1280','-ResY=720','-ExecCmds=t.MaxFPS 60,t.IdleWhenNotForeground 0,r.VSync 0,Slate.bAllowThrottling 0,r.DefaultFeature.MotionBlur 0','-Sub01HandsDiagnostic=DeskTyping','-Sub01DiagnosticSeat','-Sub01ContactFreeze=3','-Sub01LiveHome','-Sub01NativeControl='+str(control),'-Sub01DiagnosticMesh=/Game/Sub01Hands/FBX/SUB01_OriginalOwner.SUB01_OriginalOwner','-Sub01DiagnosticClip=/Game/Sub01Hands/FBX/SUB01_DeskTyping.SUB01_DeskTyping','-Sub01ContactProfile='+str(PROJECT/'unreal-skinned-contact-audit.json')]
    if args.startup_view!='desk-diagnostic':
        native=[item for item in native if not item.startswith(('-Sub01HandsDiagnostic=','-Sub01DiagnosticClip=','-Sub01ContactProfile=','-Sub01ContactFreeze=')) and item not in ('-Sub01DiagnosticSeat','-Sub01LiveHome')]
        native+=['-Sub01HandsDiagnostic=Walk','-Sub01DiagnosticClip=/Game/Sub01Hands/FBX/SUB01_Walk.SUB01_Walk']
        native+=['-Sub01LiveHome']
        if args.startup_view=='manual':native+=['-Sub01ManualView']
    saved=PROJECT/'Saved/Logs/Sub01HomeLab.log'
    initial=saved.stat().st_mtime if saved.exists()else 0
    with log.open('w')as output:
        engine=subprocess.Popen(native,env=env,stdin=subprocess.DEVNULL,stdout=output,stderr=subprocess.STDOUT)
    print('NATIVE_AUTHENTICATED_WINDOW_PID',engine.pid,flush=True)
    while time.time()<args.deadline_epoch-20:
        if engine.poll()is not None:raise SystemExit('Native window ended before actual tick')
        if saved.exists()and saved.stat().st_mtime>initial:
            proof=subprocess.run(['runuser','-u','unreal','--','grep','-m','1','SUB01_FIRST_ACTUAL_GAME_TICK',str(saved)],capture_output=True,text=True,timeout=5,env=display_env)
            if proof.returncode==0:break
        time.sleep(2)
    else:raise SystemExit('Native first tick deadline')
    print('ACTUAL_NATIVE_WINDOW_RESIZED',resize_owned_game_window(display_env),'1280x720',flush=True)
    time.sleep(8)
    movie=folder/('actual-window-'+args.startup_view+'.mp4')
    ffmpeg=['ffmpeg','-nostdin','-y','-loglevel','error','-probesize','32','-analyzeduration','0','-f','x11grab','-framerate','30','-video_size','1280x720','-i',':99.0','-t','8','-c:v','libx264','-preset','ultrafast','-crf','20','-pix_fmt','yuv420p','-movflags','+faststart',str(movie)]
    recorder=subprocess.Popen(ffmpeg,env=display_env,stdout=subprocess.DEVNULL,stderr=(BASE/'logs/native-window-ffmpeg.log').open('w'))
    time.sleep(1)
    if args.startup_view=='desk-diagnostic':control.write_text(json.dumps({'revision':101,'replayTyping':True}))
    recorder.wait(timeout=30)
    if recorder.returncode or not movie.is_file()or movie.stat().st_size<10000:raise SystemExit('Actual window recording failed')
    control.write_text(json.dumps({'revision':102,'capture':'native-headed-hands-pc.png'}))
    destination=BASE/('evidence/native/native-window-'+('typing' if args.startup_view=='desk-diagnostic' else args.startup_view)+'.mp4')
    destination.write_bytes(movie.read_bytes())
    print('ACTUAL_X11_WINDOW_MOVIE_BYTES',destination.stat().st_size,'NATIVE_KEPT_ALIVE_PID',engine.pid,flush=True)

if __name__=='__main__':main()
