"""Restore only original owner grants if an update refuses before Game exit."""
from pathlib import Path
import hashlib,json,os,shutil,time
PRIVATE=Path('/home/unreal/.sub01-private')
GAME=(215923,979985246)
def restore():
 from private_home_candidate_scope import trusted_json,proc
 assert os.getuid()==0 and proc(GAME[0])[0]==GAME[1]
 pause=trusted_json('/run/sub01-home-private/input-maintenance-pause.json');assert pause['old_game_identity']==list(GAME)and pause['purpose']=='owner-requested-localhost-update'
 backup=Path(pause['backup']).resolve();assert backup.parent==PRIVATE and backup.name.startswith('owner-update-input-pause-')
 privacy=json.loads((PRIVATE/'native-view-privacy.json').read_text());assert(privacy['native_pid'],privacy['native_start_ticks'])==GAME and 0<=time.time()-privacy['captured_utc']<2 and privacy['view_mode']=='manual'
 for name in ['native-viewer-input-enabled','native-viewer-capture-enabled']:
  source=backup/name;raw=source.read_bytes();value=json.loads(raw);assert(value['native_pid'],value['native_start_ticks'])==GAME
  assert hashlib.sha256(raw).hexdigest()==pause['grant_sha256'][name]
  target=PRIVATE/name;temporary=target.with_suffix('.restore.tmp');temporary.write_bytes(raw);os.chown(temporary,1001,1001);temporary.chmod(0o600);os.replace(temporary,target)
 # Existing viewer physical-privacy checks continue to censor capture and allow
 # only the pre-existing blind exit controls when the camera is private.
 return {'original_owner_grants_restored':True,'same_game_identity':list(GAME),'physical_privacy_guards_unchanged':True,'camera_or_backend_changed':False}
if __name__=='__main__':print(json.dumps(restore()))
