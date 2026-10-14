"""Record the real authenticated X11 native game window, never a movie camera."""
import argparse,json,math,os,re,secrets,subprocess,time,uuid
from pathlib import Path
from unreal_runtime_environment import build_unreal_environment
from unreal_native_display import allocated_a40_bus_id,nvidia_xorg_config,xorg_command,owned_xorg_pid,resize_owned_game_window

BASE=Path('/workspace/sub01-home-private')
PROJECT=BASE/'project/Sub01HomeLab'
PRIVATE=Path('/home/unreal/.sub01-private')

def phone_review_arguments(pose_time, offset=None, euler=None):
    """Explicit original-clip review; never grants ordinary phone readiness."""
    if not math.isfinite(pose_time) or not 0 <= pose_time <= 60:
        raise ValueError('Phone review time must be finite and within 0–60 seconds')
    if (offset is None) != (euler is None):
        raise ValueError('Phone candidate requires both measured offset and rotation')
    result=['-Sub01HandsDiagnostic=Phone',
            '-Sub01DiagnosticClip=/Game/Sub01Hands/FBX/SUB01_Phone.SUB01_Phone',
            '-Sub01PhoneGripDiagnostic', f'-Sub01PhonePoseTime={pose_time:g}']
    if offset is not None:
        values=[]
        for text, labels in [(offset, ('X','Y','Z')), (euler, ('P','Y','R'))]:
            pattern=r'\s*'+r'\s+'.join(label+r'=([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)' for label in labels)+r'\s*'
            match=re.fullmatch(pattern,text)
            if not match:raise ValueError('Phone candidate must contain exactly three measured numeric fields')
            triple=tuple(float(x) for x in match.groups())
            if not all(math.isfinite(x) for x in triple):raise ValueError('Nonfinite phone candidate')
            values.append(triple)
        if math.sqrt(sum(x*x for x in values[0]))>30 or any(abs(x)>180 for x in values[1]):
            raise ValueError('Phone candidate exceeds the native diagnostic bounds')
        result+=['-Sub01PhoneMountCm='+offset,'-Sub01PhoneMountEuler='+euler]
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--deadline-epoch',type=int,required=True)
    parser.add_argument('--display-provider',choices=('xvfb','nvidia-xorg'),default='xvfb')
    parser.add_argument('--reuse-display',action='store_true')
    parser.add_argument('--startup-view',choices=('manual','live','desk-diagnostic','phone-diagnostic'),default='manual')
    parser.add_argument('--review-typing-hover',action='store_true',help='Explicit distal-surface pose review; no seating or key-contact acceptance')
    parser.add_argument('--phone-pose-time',type=float,default=4)
    parser.add_argument('--phone-mount-offset')
    parser.add_argument('--phone-mount-euler')
    parser.add_argument('--phone-head-camera',action='store_true',help='Explicit captured Head-origin diagnostic camera; no normal activity acceptance')
    parser.add_argument('--phone-eye-camera',action='store_true',help='Explicit measured iris-surface camera review; no normal activity or grip acceptance')
    args=parser.parse_args()
    if args.review_typing_hover and args.startup_view!='desk-diagnostic':raise SystemExit('Typing hover review requires explicit desk diagnostic')
    if args.startup_view!='phone-diagnostic' and (args.phone_mount_offset or args.phone_mount_euler):raise SystemExit('Phone mount requires explicit phone diagnostic')
    if args.phone_head_camera and args.startup_view!='phone-diagnostic':raise SystemExit('Head-origin camera requires explicit phone diagnostic')
    if args.phone_eye_camera and args.startup_view!='phone-diagnostic':raise SystemExit('Measured eye camera requires explicit phone diagnostic')
    if args.phone_eye_camera and (args.phone_head_camera or args.phone_pose_time!=4):raise SystemExit('Measured eye camera requires its original 4s witness and no Head-origin flag')
    phone_args=phone_review_arguments(args.phone_pose_time,args.phone_mount_offset,args.phone_mount_euler) if args.startup_view=='phone-diagnostic' else []
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
    if args.review_typing_hover:native.append('-Sub01ReviewTypingHover')
    if args.startup_view=='phone-diagnostic':
        native=[item for item in native if not item.startswith(('-Sub01HandsDiagnostic=','-Sub01DiagnosticClip=','-Sub01ContactProfile=','-Sub01ContactFreeze=')) and item not in ('-Sub01DiagnosticSeat','-Sub01LiveHome')]
        native+=phone_args
        if args.phone_head_camera:native.append('-Sub01PhoneHeadCamera')
        if args.phone_eye_camera:native.append('-Sub01PhoneEyeCamera')
    elif args.startup_view!='desk-diagnostic':
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
    control.write_text(json.dumps({'revision':102,'capture':'native-phone-grip-review.png' if args.startup_view=='phone-diagnostic' else 'native-headed-hands-pc.png'}))
    destination=BASE/('evidence/native/native-window-'+('typing' if args.startup_view=='desk-diagnostic' else args.startup_view)+'.mp4')
    destination.write_bytes(movie.read_bytes())
    print('ACTUAL_X11_WINDOW_MOVIE_BYTES',destination.stat().st_size,'NATIVE_KEPT_ALIVE_PID',engine.pid,flush=True)

if __name__=='__main__':main()
