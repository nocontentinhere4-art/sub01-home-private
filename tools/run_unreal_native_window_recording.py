"""Record the real authenticated X11 native game window, never a movie camera."""
import argparse,json,os,secrets,subprocess,time,uuid
from pathlib import Path
from unreal_runtime_environment import build_unreal_environment

BASE=Path('/workspace/sub01-home-private')
PROJECT=BASE/'project/Sub01HomeLab'
PRIVATE=Path('/home/unreal/.sub01-private')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--deadline-epoch',type=int,required=True)
    args=parser.parse_args()
    remaining=args.deadline_epoch-time.time()
    if remaining<90:raise SystemExit('Authorized window too short')
    PRIVATE.mkdir(mode=0o700,parents=True,exist_ok=True)
    os.chown(PRIVATE,1001,1001);PRIVATE.chmod(0o700)
    auth=PRIVATE/'native-xauthority';auth.touch(mode=0o600);os.chown(auth,1001,1001);auth.chmod(0o600)
    cookie=secrets.token_hex(16)
    subprocess.run(['runuser','-u','unreal','--','xauth','-f',str(auth),'source','-'],input=f'add :99 . {cookie}\n',text=True,stdout=subprocess.DEVNULL,check=True)
    env=build_unreal_environment();env.update(DISPLAY=':99',XAUTHORITY=str(auth),SDL_VIDEODRIVER='x11')
    display_env={k:v for k,v in env.items()if not k.startswith('SUB01_')}
    log=BASE/'logs/native-headed-window.log'
    folder=PRIVATE/('window-record-'+uuid.uuid4().hex);folder.mkdir(mode=0o700);os.chown(folder,1001,1001)
    xlog=(BASE/'logs/native-xvfb.log').open('w')
    xvfb=subprocess.Popen(['runuser','-u','unreal','--','timeout',str(int(remaining)),'Xvfb',':99','-nolisten','tcp','-screen','0','1280x720x24','-auth',str(auth)],env=display_env,stdout=xlog,stderr=subprocess.STDOUT)
    time.sleep(2)
    if xvfb.poll()is not None:raise SystemExit('Private X server failed')
    control=PRIVATE/'native-control.json'
    control.write_text(json.dumps({'revision':100}));os.chown(control,1001,1001);control.chmod(0o600)
    native=['runuser','-u','unreal','--','timeout','--kill-after=5',str(max(1,int(args.deadline_epoch-time.time()))),'/workspace/sub01-unreal/UE/Engine/Binaries/Linux/UnrealEditor-Cmd',str(PROJECT/'Sub01HomeLab.uproject'),'/Game/Sub01Home/ActualHome','-game','-vulkan','-corelimit=8','-ZenDataPath=/workspace/sub01-unreal/cache/zen','-unattended','-NoSound','-NoSplash','-windowed','-NoBorder','-WinX=0','-WinY=0','-ResX=1280','-ResY=720','-ExecCmds=t.MaxFPS 60,t.IdleWhenNotForeground 0,r.VSync 0,Slate.bAllowThrottling 0,r.DefaultFeature.MotionBlur 0','-Sub01HandsDiagnostic=DeskTyping','-Sub01DiagnosticSeat','-Sub01ContactFreeze=3','-Sub01LiveHome','-Sub01NativeControl='+str(control),'-Sub01DiagnosticMesh=/Game/Sub01Hands/FBX/SUB01_OriginalOwner.SUB01_OriginalOwner','-Sub01DiagnosticClip=/Game/Sub01Hands/FBX/SUB01_DeskTyping.SUB01_DeskTyping','-Sub01ContactProfile='+str(PROJECT/'unreal-skinned-contact-audit.json')]
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
    time.sleep(8)
    movie=folder/'actual-window-typing.mp4'
    ffmpeg=['ffmpeg','-y','-loglevel','error','-f','x11grab','-framerate','30','-video_size','1280x720','-i',':99.0','-t','8','-c:v','libx264','-preset','ultrafast','-crf','20','-pix_fmt','yuv420p','-movflags','+faststart',str(movie)]
    recorder=subprocess.Popen(ffmpeg,env=display_env,stdout=subprocess.DEVNULL,stderr=(BASE/'logs/native-window-ffmpeg.log').open('w'))
    time.sleep(1)
    control.write_text(json.dumps({'revision':101,'replayTyping':True}))
    recorder.wait(timeout=30)
    if recorder.returncode or not movie.is_file()or movie.stat().st_size<10000:raise SystemExit('Actual window recording failed')
    control.write_text(json.dumps({'revision':102,'capture':'native-headed-hands-pc.png'}))
    destination=BASE/'evidence/native/native-window-typing.mp4'
    destination.write_bytes(movie.read_bytes())
    print('ACTUAL_X11_WINDOW_MOVIE_BYTES',destination.stat().st_size,'NATIVE_KEPT_ALIVE_PID',engine.pid,flush=True)

if __name__=='__main__':main()
