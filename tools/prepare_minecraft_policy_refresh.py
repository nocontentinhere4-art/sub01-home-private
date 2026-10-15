"""Save and verify actual private game/guest state before a policy-only restart.
No gameplay input, world reset, renderer/Game/pod stop, or credentials output.
"""
import hashlib,json,os,shutil,stat,time,urllib.request
from pathlib import Path
ROOT=Path('/workspace/sub01-home-private');PRIVATE=Path('/home/unreal/.sub01-private');BACKEND=Path('/home/unreal/sub01-backend')
EXPECTED={158534:976752252,158535:976752327,158580:976753319,62755:975065256,62757:975065274,193148:978377926}
PROJECT=b'/workspace/sub01-private-playable-14acd9d355c6/Sub01HomeLab/Sub01HomeLab.uproject'
assert os.getuid()==1001
window=Path('/run/sub01-home-private/runtime-window.json');m=window.stat();w=json.loads(window.read_text());assert m.st_uid==0 and not m.st_mode&0o022 and w['pod']=='dgtgepkz7h1zy5'and w['stop_guards_authenticated']and time.time()<w['deadline_epoch']-300
for pid,start in EXPECTED.items():
 p=Path('/proc')/str(pid);assert int((p/'status').read_text().split('Uid:')[1].split()[0])==1001;assert int((p/'stat').read_text().rsplit(')',1)[1].split()[19])==start
args=(Path('/proc/193148/cmdline')).read_bytes().split(b'\0');assert PROJECT in args and b'-game'in args
assert b'live_server.py'in Path('/proc/158534/cmdline').read_bytes().split(b'\0')
assert b'/workspace/sub01-home-private/backend-state/minecraft/server.jar'in Path('/proc/158535/cmdline').read_bytes().split(b'\0')
assert b'/home/unreal/sub01-backend/computer/worker.cjs'in Path('/proc/62757/cmdline').read_bytes().split(b'\0')
focus=json.loads((PRIVATE/'native-tv-focus.json').read_text());assert focus.get('focused')is False
state=json.load(urllib.request.urlopen('http://127.0.0.1:8820/api/home',timeout=3));assert not state['minecraft']['active']
source=BACKEND/'home_minecraft_input.py';assert hashlib.sha256(source.read_bytes()).hexdigest()=='d52edeaaedeae5d597731532f5b40a3af62334dd4f067545e2d882930013b386'
stamp=time.strftime('%Y%m%dT%H%M%SZ',time.gmtime());out=ROOT/('minecraft-policy-refresh-'+stamp);out.mkdir(mode=0o700);report={'schema':'sub01.exact-minecraft-policy-save-preflight.v1','started_utc':stamp,'process_identities':EXPECTED,'game_untouched':True,'pc_guest_untouched':True,'minecraft_before':state['minecraft']}
log=ROOT/'backend-state/minecraft/server.log';offset=log.stat().st_size;requested=time.time()
with Path('/proc/158535/fd/0').open('wb',buffering=0)as stream:stream.write(b'save-all flush\n')
ack=None
for _ in range(100):
 with log.open('rb')as stream:stream.seek(offset);tail=stream.read().decode(errors='replace')
 if 'Saved the game'in tail:ack=tail;break
 time.sleep(.1)
assert ack,'Actual Java save-all flush ACK missing; no restart permitted'
report['minecraft_flush_ack']=ack;report['minecraft_flush_requested_epoch']=requested
# Saving the existing v86 guest is maintenance only; no keyboard/session changes.
env=dict(v.split(b'=',1)for v in Path('/proc/62757/environ').read_bytes().split(b'\0')if b'='in v);snapshot=Path(env[b'SUB01_VM_STATE'].decode());old=snapshot.stat();requested=time.time()
with Path('/proc/62757/fd/0').open('wb',buffering=0)as stream:stream.write(b'{"type":"save"}\n')
for _ in range(100):
 current=snapshot.stat()
 if current.st_ino!=old.st_ino and current.st_mtime>=requested-1:break
 time.sleep(.1)
else:raise RuntimeError('Fresh atomic PC snapshot missing; no restart permitted')
assert current.st_size>1024*1024
shutil.copy2(snapshot,out/'computer-graphical.bin');pc_hash=hashlib.sha256((out/'computer-graphical.bin').read_bytes()).hexdigest();assert pc_hash==hashlib.sha256(snapshot.read_bytes()).hexdigest();report['pc_snapshot']={'source':str(snapshot),'bytes':current.st_size,'sha256':pc_hash,'atomic_save_completed_after_request':True}
world=ROOT/'backend-state/minecraft/world';shutil.copytree(world,out/'world',ignore=shutil.ignore_patterns('session.lock'));manifest=[]
for f in sorted((out/'world').rglob('*')):
 if not f.is_file():continue
 original=world/f.relative_to(out/'world');digest=hashlib.sha256(f.read_bytes()).hexdigest();assert digest==hashlib.sha256(original.read_bytes()).hexdigest();manifest.append({'relative':str(f.relative_to(out/'world')),'bytes':f.stat().st_size,'sha256':digest})
assert any(x['relative']=='level.dat'for x in manifest);report['world_files']=manifest;report['world_playerdata_files']=[x for x in manifest if x['relative'].startswith('playerdata/')];assert report['world_playerdata_files']
for name in ['home.json','state.json','memory.json']:
 p=ROOT/'backend-state'/name
 if p.exists():shutil.copy2(p,out/name)
shutil.copy2(source,out/'home_minecraft_input.before.py');shutil.copy2(PRIVATE/'device-runtime-launch-current.py',out/'device-runtime-launch-current.before.py')
for f in out.iterdir():
 if f.is_file():f.chmod(0o600)
report['restart_preconditions_verified']=True;report['snapshot_directory']=str(out);report['snapshot_finished_epoch']=time.time();(out/'preflight.json').write_text(json.dumps(report,indent=2));(out/'preflight.json').chmod(0o600);print(json.dumps({'snapshot_directory':str(out),'world_files':len(manifest),'world_player_files':len(report['world_playerdata_files']),'pc_snapshot_sha256':pc_hash,'actual_java_flush_ack':True,'restart_preconditions_verified':True}),flush=True)
