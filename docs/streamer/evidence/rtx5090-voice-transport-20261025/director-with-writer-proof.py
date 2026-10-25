"""Diagnostic launcher for pinned original director; writer proof only."""
import hashlib,json,os,runpy,stat,sys,time
from pathlib import Path
SOURCE=Path('/home/unreal/.sub01-private/latest-source-20261023/scripts/streamer_director.py')
if hashlib.sha256(SOURCE.read_bytes()).hexdigest()!='d7ff873b40ac390c2004c248e5aa825255bcefd49e44684a077b78d91c799b8c':raise SystemExit('Director source changed')
config=Path(os.environ['SUB01_WRITER_CONFIG']);snapshot=Path(os.environ['SUB01_WRITER_SNAPSHOT'])
validator=Path('/tmp/sub01-share/voice-writer-proof-validation.py')
if hashlib.sha256(validator.read_bytes()).hexdigest()!='2bea39a3cf92ba05c9fc1fb84154521607bfd347b024e815c2e2557950eba63d':raise SystemExit('Validator changed')
validation=runpy.run_path(str(validator));read_file=validation['read_file']
targets=read_file(config)
if not validation['targets_ok'](targets):raise SystemExit('Target pins invalid/duplicate')
known={tuple(t['fifo']):t for t in targets}
module=runpy.run_path(str(SOURCE),run_name='sub01_director_diagnostic')
scope=module['main_status'].__globals__;original=scope['fifo_has_writer']
def checked_writer(st,proc_root='/proc'):
 identity=(st.st_dev,st.st_ino);target=known.get(identity)
 if target is None:return original(st,proc_root)
 try:
  return validation['valid'](read_file(snapshot),target,time.monotonic())
 except (OSError,ValueError,TypeError,KeyError,RuntimeError):return False
scope['fifo_has_writer']=checked_writer
sys.exit(module['main']())
