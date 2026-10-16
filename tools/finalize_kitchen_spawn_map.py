"""Finalize only two verified PlayerStarts after an independently verified preseal.

Run as the existing project owner. Root updates its approval separately after
this returns; no grants, live files, renderer or backend are changed here.
"""
from pathlib import Path
import copy,hashlib,json,os,re,shutil,time
CANDIDATE=Path('/workspace/sub01-private-candidate-20261015/Sub01HomeLab')
LIVE=Path('/workspace/sub01-private-playable-next-20261016/Sub01HomeLab')
TARGET=Path('/workspace/sub01-private-playable-kitchen-r1-20261016/Sub01HomeLab')
GAME=(215923,979985246)
MAP='Content/Sub01Home/ActualHome.umap'
MODULE='e571937b708c8e860d05373f1d3de428bc22a4c547cf80ded1ef80db706ace96'
CONFIG='a46b973bc17d64a11743ef5fc04b12e0ee8b0a65feb0a2ec72944964f3fc40eb'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def updated_receipt(old,expected_old,new_sha,new_bytes,pose_sha):
 assert old['map_sha256']==expected_old and old['all_file_hashes_verified']and old['independent_writable_copies']
 assert re.fullmatch('[0-9a-f]{64}',new_sha)and re.fullmatch('[0-9a-f]{64}',pose_sha)and type(new_bytes)is int and new_bytes>0
 matches=[(i,r)for i,r in enumerate(old['files'])if r['path']==MAP];assert len(matches)==1
 index,row=matches[0];assert row['sha256']==expected_old
 new=copy.deepcopy(old);new['files'][index].update(sha256=new_sha,bytes=new_bytes)
 assert [r for r in new['files']if r['path']!=MAP]==[r for r in old['files']if r['path']!=MAP]
 new.update(map_sha256=new_sha,bytes=sum(r['bytes']for r in new['files']),spawn_only_finalization={'prior_map_sha256':expected_old,'pose_receipt_sha256':pose_sha,'only_existing_playerstarts_changed':True},epoch=time.time())
 return new

def run():
 from private_home_candidate_scope import trusted_json,proc,SCOPE
 from unreal_editor_task_queue import guard_valid
 assert os.getuid()==1001 and guard_valid(now=time.time()+180)
 a=trusted_json('/run/sub01-home-private/promotion-approved.json');pause=trusted_json('/run/sub01-home-private/input-maintenance-pause.json');pose=trusted_json('/run/sub01-home-private/next-pawn-pose-approved.json')
 assert a['execute_handoff']is False and a['old_game_identity']==list(GAME)and a['playable_project']==str(TARGET)and a['source_project']==str(CANDIDATE)
 assert pause['old_game_identity']==list(GAME)and pause['purpose']=='owner-requested-localhost-update'and 0<=time.time()-pause['started_epoch']<600
 assert(pose['native_pid'],pose['native_start_ticks'])==GAME and pose['accepted_inputs']==pause['accepted_inputs']and 0<=time.time()-pose['captured_epoch']<120
 identity=proc(GAME[0]);assert identity[0]==GAME[1]and identity[1]!='Z'and str(LIVE/'Sub01HomeLab.uproject').encode()in identity[2]
 scope=trusted_json(SCOPE);assert(scope['editor_pid'],scope['editor_start_ticks'])==(203351,978985107)and proc(203351)[0]==978985107
 name=a['spawn_pose_result'];assert re.fullmatch(r'\d{3}-preserve_spawn_pose-result\.json',name)
 proofpath=CANDIDATE/'private-audit'/name;proof=json.loads(proofpath.read_text());v=proof['result']
 assert proof['ok']and proof['editor_pid']==203351 and proof['original_game_preserved']and proof['task']=='preserve_spawn_pose'
 assert v['saved']and v['source_game_identity']==list(GAME)and v['only_existing_two_playerstarts_changed']and len(v['before'])==len(v['after'])==2
 assert v['location']==pose['location']and v['rotation']==pose['rotation']
 receipt=TARGET/'private-audit/playable-copy.json';old=json.loads(receipt.read_text());expected=a['map_sha256']
 assert old['playable_project']==str(TARGET)and old['source_project']==str(CANDIDATE)and old['map_sha256']==expected
 assert sha(TARGET/MAP)==expected==sha(Path(v['backup'])/'ActualHome.umap')
 for project in (LIVE,TARGET):
  assert sha(project/'Binaries/Linux/libUnrealEditor-Sub01HomeLab.so')==MODULE and sha(project/'Config/DefaultGame.ini')==CONFIG
 assert sha(LIVE/MAP)==scope['live_map_sha256']
 new_sha=sha(CANDIDATE/MAP);assert new_sha==v['map_sha256']
 planned=updated_receipt(old,expected,new_sha,(CANDIDATE/MAP).stat().st_size,sha(proofpath))
 backup=TARGET/'Saved/PrivateMapBackups'/('spawn-only-finalization-'+str(time.time_ns()));backup.mkdir(parents=True)
 shutil.copy2(TARGET/MAP,backup/'ActualHome.umap');shutil.copy2(receipt,backup/'playable-copy.json')
 temp=(TARGET/MAP).with_suffix('.umap.spawn.tmp');temp_receipt=receipt.with_suffix('.spawn.tmp')
 try:
  shutil.copy2(CANDIDATE/MAP,temp);assert sha(temp)==new_sha
  assert (temp.stat().st_dev,temp.stat().st_ino)!=( (CANDIDATE/MAP).stat().st_dev,(CANDIDATE/MAP).stat().st_ino)
  temp_receipt.write_text(json.dumps(planned,indent=2)+'\n');os.replace(temp,TARGET/MAP);os.replace(temp_receipt,receipt)
  assert sha(TARGET/MAP)==new_sha and sha(CANDIDATE/MAP)==new_sha and proc(GAME[0])[0]==GAME[1]
  result={'schema':'sub01.spawn-only-sealed-map-finalization.v1','saved':True,'target_project':str(TARGET),'preseal_map_sha256':expected,'map_sha256':new_sha,'playable_copy_sha256':sha(receipt),'pose_receipt':str(proofpath),'pose_receipt_sha256':sha(proofpath),'accepted_inputs':pose['accepted_inputs'],'all_other_manifest_rows_unchanged':True,'backup':str(backup),'live_files_or_processes_changed':False,'epoch':time.time()}
  (TARGET/'private-audit/spawn-only-finalization.json').write_text(json.dumps(result,indent=2)+'\n');return result
 except Exception:
  shutil.copy2(backup/'ActualHome.umap',temp);os.replace(temp,TARGET/MAP);shutil.copy2(backup/'playable-copy.json',temp_receipt);os.replace(temp_receipt,receipt)
  assert sha(TARGET/MAP)==expected and receipt.read_bytes()==(backup/'playable-copy.json').read_bytes();raise
if __name__=='__main__':print(json.dumps(run()))
