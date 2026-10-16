"""Two-phase exact next-Game policy refresh; import has no side effects.

Call preflight_before_handoff while oldGame is alive, then apply_after_launch
only after the sole native owner launches the exact next private Game. Reuses
proven flush/snapshot/graceful-backend-only recipes; never stops Game/pod/VM.
"""
import ast,hashlib,json,os,re,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
NEXT_PROJECT='/workspace/sub01-private-playable-kitchen-r1-20261016/Sub01HomeLab/Sub01HomeLab.uproject'
OLD_PROJECT='/workspace/sub01-private-playable-next-20261016/Sub01HomeLab/Sub01HomeLab.uproject'
OLD_GAME=(215923,979985246);BACKEND=(217597,980033668);PC=(62755,975065256);VM=(62757,975065274)
POLICY_SHA='7586b04ae2e5703dc650f34643900f3ad13a678ab8500e7ff3d16f757160b606'
TEMPLATE_SHA={'prepare_minecraft_policy_refresh_r2.py': '1c4b058e8569ae5219079300de69641099c96bc25a61747238e86f0198b8b92d', 'apply_minecraft_policy_refresh.py': '2dc996601b982e862816ce5f21480ccd12e18896075f35b4653b79c0db92ab97'}

def template(name):
 raw=(HERE/name).read_bytes();assert hashlib.sha256(raw).hexdigest()==TEMPLATE_SHA[name],'Exact proven maintenance recipe required';return raw.decode()

def proc(pid,start=None):
 p=Path('/proc')/str(pid);s=(p/'stat').read_text().rsplit(')',1)[1].split();uid=int((p/'status').read_text().split('Uid:')[1].split()[0]);ticks=int(s[19]);args=(p/'cmdline').read_bytes().split(b'\0')
 assert uid==1001 and s[0]!='Z' and (start is None or ticks==start)
 return ticks,args

def exact_game(pid,start,project):
 assert type(pid)is int and pid>0 and type(start)is int and start>0
 ticks,args=proc(pid,start);assert project.encode()in args and b'-game'in args
 return True

def policy_for_next(text,pid,start):
 assert type(pid)is int and pid>0 and type(start)is int and start>0
 wanted={'PROJECT':NEXT_PROJECT,'NATIVE_PID':pid,'NATIVE_START_TICKS':start};old={'PROJECT':OLD_PROJECT,'NATIVE_PID':OLD_GAME[0],'NATIVE_START_TICKS':OLD_GAME[1]};spans={}
 for n in ast.parse(text).body:
  if isinstance(n,ast.Assign):
   for t in n.targets:
    if isinstance(t,ast.Name)and t.id in wanted:
     assert t.id not in spans and ast.literal_eval(n.value)==old[t.id],'Exact old policy binding required'
     spans[t.id]=(n.lineno,n.end_lineno)
 assert set(spans)==set(wanted)
 lines=text.splitlines(keepends=True)
 for name,(lo,hi)in sorted(spans.items(),key=lambda row:row[1][0],reverse=True):lines[lo-1:hi]=[name+' = '+repr(wanted[name])+'\n']
 result=''.join(lines);ast.parse(result);return result

def current_services():
 assert os.getuid()==1001;exact_game(*OLD_GAME,OLD_PROJECT)
 for identity in (BACKEND,PC,VM):proc(*identity)
 assert b'live_server.py'in proc(*BACKEND)[1]
 children=(Path('/proc')/str(BACKEND[0])/'task'/str(BACKEND[0])/'children').read_text().split();java=[];worker=[]
 for pid in map(int,children):
  ticks,args=proc(pid)
  if b'/workspace/sub01-home-private/backend-state/minecraft/server.jar'in args:java.append((pid,ticks))
  elif b'/home/unreal/sub01-backend/games/minecraft/worker.cjs'in args:worker.append((pid,ticks))
 assert len(java)==len(worker)==1,'Exact existing Java/Minecraft worker children required'
 return java[0],worker[0]

def preflight_before_handoff():
 java,worker=current_services();text=template('prepare_minecraft_policy_refresh_r2.py')
 ids={BACKEND[0]:BACKEND[1],java[0]:java[1],worker[0]:worker[1],PC[0]:PC[1],VM[0]:VM[1],OLD_GAME[0]:OLD_GAME[1]}
 text=re.sub(r'^EXPECTED=.*$', 'EXPECTED='+repr(ids),text,flags=re.M)
 for old,new in [('158534',str(BACKEND[0])),('158535',str(java[0])),('158580',str(worker[0])),('976752252',str(BACKEND[1])),('976752327',str(java[1])),('976753319',str(worker[1])),('d52edeaaedeae5d597731532f5b40a3af62334dd4f067545e2d882930013b386',POLICY_SHA)]:text=text.replace(old,new)
 text=text.replace('/workspace/sub01-private-playable-14acd9d355c6/Sub01HomeLab/Sub01HomeLab.uproject',OLD_PROJECT).replace('193148',str(OLD_GAME[0])).replace('978377926',str(OLD_GAME[1]))
 namespace={'__name__':'__sub01_guarded_preflight__'};exec(compile(text,'<proven-next-game-save-preflight>','exec'),namespace)
 out=namespace['out'];report=namespace['report'];assert report['restart_preconditions_verified'];return str(out)

def apply_after_launch(snapshot_directory,next_pid,next_start):
 """Explicit native-owner call only, after actual newGame PID/start known."""
 assert os.getuid()==1001;exact_game(next_pid,next_start,NEXT_PROJECT)
 try:proc(*OLD_GAME)
 except (OSError,AssertionError):pass
 else:raise RuntimeError('OldGame still alive; no backend refresh permitted')
 snap=Path(snapshot_directory).resolve();assert snap.parent==Path('/workspace/sub01-home-private') and snap.name.startswith('minecraft-policy-refresh-')
 pre=json.loads((snap/'preflight.json').read_text());assert pre['restart_preconditions_verified'] and time.time()-pre['snapshot_finished_epoch']<600
 ids={int(k):v for k,v in pre['process_identities'].items()};assert ids[BACKEND[0]]==BACKEND[1] and ids[PC[0]]==PC[1]and ids[VM[0]]==VM[1]
 for identity in (BACKEND,PC,VM):proc(*identity)
 # Identify only the already-saved exact Java/worker; never select new services.
 remaining={k:v for k,v in ids.items()if k not in (BACKEND[0],PC[0],VM[0],OLD_GAME[0])};assert len(remaining)==2
 java=worker=None
 for pid,ticks in remaining.items():
  _,args=proc(pid,ticks)
  if b'/workspace/sub01-home-private/backend-state/minecraft/server.jar'in args:java=(pid,ticks)
  elif b'/home/unreal/sub01-backend/games/minecraft/worker.cjs'in args:worker=(pid,ticks)
 assert java and worker
 source=Path('/home/unreal/sub01-backend/home_minecraft_input.py');raw=source.read_bytes();assert hashlib.sha256(raw).hexdigest()==POLICY_SHA
 next_source=policy_for_next(raw.decode(),next_pid,next_start);staged=Path('/home/unreal/runtime-tools/home_minecraft_input.next-promoted.py');staged.write_text(next_source);staged.chmod(0o600);newsha=hashlib.sha256(staged.read_bytes()).hexdigest()
 text=template('apply_minecraft_policy_refresh.py');text=text.replace("SNAP=ROOT/'minecraft-policy-refresh-20261015T202040Z'",'SNAP=Path('+repr(str(snap))+')')
 text=text.replace('/home/unreal/runtime-tools/home_minecraft_input.promoted.py',str(staged))
 replacements=[('d52edeaaedeae5d597731532f5b40a3af62334dd4f067545e2d882930013b386',POLICY_SHA),('dcdd6475befb566f421ee4f4f26b03c03a6ae3d8d7ce8c507e1dbecb2becb3b5',newsha)]
 # Avoid replacing the newly substituted OLD hash a second time.
 text=text.replace(replacements[0][0],'__OLD_POLICY_SHA__').replace(replacements[1][0],newsha).replace('__OLD_POLICY_SHA__',POLICY_SHA)
 for old,new in [('158534',str(BACKEND[0])),('158535',str(java[0])),('158580',str(worker[0])),('976752252',str(BACKEND[1])),('976752327',str(java[1])),('976753319',str(worker[1])),('193148',str(next_pid)),('978377926',str(next_start))]:text=text.replace(old,new)
 exec(compile(text,'<proven-next-game-backend-refresh>','exec'),{'__name__':'__sub01_guarded_backend_refresh__'})
 return json.loads((snap/'rollout.json').read_text())
