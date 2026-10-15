"""Deploy the receipt-pinned realistic home candidate after its saved Editor exits."""
import hashlib,json,os,shutil,subprocess,time
from pathlib import Path
from launch_private_persistent_editor import PROJECT,PRIVATE,verified_window
SIBLING=Path('/workspace/sub01-private-native-build/Sub01HomeLab')
MODULE_SHA='97c3395e01e03c2df5f549c7920df289fa69a1073bee71c0b9a93fbfe8f5506a'
SOURCE_SHA='be016bca02559ab0981c4fe0642264395978b8db8fbff1fce41e80abfb48ceef'
HEADER_SHA='bda916f22a5bc114660454b3d8a0dd16f8f09dab00be829ae94153b2126ba5de'
OLD_MODULE='089345fa2c32f843fc4d4dad17d0d63afcb70bef25030d8f716c0800292072c4'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def deploy():
 verified_window(Path('/run/sub01-home-private/runtime-window.json'))
 for p in Path('/proc').iterdir():
  if not p.name.isdigit():continue
  try:assert not ((p/'comm').read_text().startswith('UnrealEditor')and(p/'stat').read_text().rsplit(')',1)[1].split()[0]!='Z'),'Live native process: never replace module'
  except OSError:pass
 r=json.loads((SIBLING/'realistic-home-native-build-result.json').read_text())
 assert r['schema']=='sub01.coherent-native-home-build.v1'and r['status']=='finished'and r['exit']==0 and r['module_sha256']==MODULE_SHA
 assert sha(SIBLING/'Source/Sub01HomeLab/Sub01HomeLab.cpp')==SOURCE_SHA and sha(SIBLING/'Source/Sub01HomeLab/Sub01HomeLab.h')==HEADER_SHA
 src=SIBLING/'Binaries/Linux';dst=PROJECT/'Binaries/Linux'
 names=['libUnrealEditor-Sub01HomeLab.so','libUnrealEditor-Sub01HomeLab.debug','libUnrealEditor-Sub01HomeLab.sym','UnrealEditor.modules','Sub01HomeLabEditor.target']
 hashes={n:sha(src/n)for n in names};assert hashes[names[0]]==MODULE_SHA
 assert sha(dst/names[0])==OLD_MODULE
 assert json.loads((src/'UnrealEditor.modules').read_text())['BuildId']=='55116800'
 saved=json.loads((PROJECT/'private-audit/saved-editor-game-handoff.json').read_text());assert sha(Path(saved['map']))==saved['map_sha256']
 backup=PRIVATE/('pre-realistic-home-binary-'+str(time.time_ns()));backup.mkdir(mode=0o700)
 before={}
 for n in names:
  if(dst/n).exists():shutil.copy2(dst/n,backup/n);before[n]=sha(dst/n)
 for n in names:
  pending=dst/('.'+n+'.coherent-new')
  assert not pending.exists()
  code='import hashlib,os,shutil,sys;from pathlib import Path;s,t,d,h=sys.argv[1:];shutil.copy2(s,t);assert hashlib.sha256(Path(t).read_bytes()).hexdigest()==h;os.replace(t,d)'
  subprocess.run(['/usr/sbin/runuser','-u','unreal','--','python3','-c',code,str(src/n),str(pending),str(dst/n),hashes[n]],check=True)
 proof={'schema':'sub01.private-coherent-home-deployment.v1','deployed_epoch':time.time(),'backup':str(backup),'before':before,'after':hashes,'source_cpp_sha256':SOURCE_SHA,'header_sha256':HEADER_SHA,'map_sha256':saved['map_sha256'],'native_game_accepted':False,'contact_gates_changed':False}
 (PRIVATE/'coherent-home-binary-deployment.json').write_text(json.dumps(proof,indent=2)+'\n');print('ACTUAL_COHERENT_MODULE_DEPLOYED',MODULE_SHA,flush=True)
 return proof
