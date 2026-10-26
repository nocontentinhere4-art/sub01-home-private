import importlib.util,json,tempfile,unittest,os,stat
from pathlib import Path
from unittest.mock import Mock,patch
P=Path(__file__).resolve().parents[1]/'tools/private_backend_coordinator.py'
spec=importlib.util.spec_from_file_location('private_backend_coordinator',P);c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
class CoordinatorTests(unittest.TestCase):
 def snapshot(self,p,n=302):
  p.mkdir();(p/'state.json').write_text(json.dumps({'engine':{},'memory':[{}]*n}));(p/'nested').mkdir();(p/'nested'/'memory.db-wal').write_bytes(b'preserved companion');(p/'memory.db-shm').write_bytes(b'companion')
 def test_complete_copy_count_and_original_unchanged(self):
  with tempfile.TemporaryDirectory()as d:
   p=Path(d);self.snapshot(p/'original');before=c.tree_manifest(p/'original');result=c.copy_state(p/'original',p/'new')
   self.assertEqual(result,before);self.assertEqual(c.tree_manifest(p/'new'),before);self.assertEqual(c.tree_manifest(p/'original'),before)
 def test_wrong_count_on_new_copy_blocks(self):
  with tempfile.TemporaryDirectory()as d:
   p=Path(d);self.snapshot(p/'original',301)
   with self.assertRaisesRegex(c.Refusal,'NEW_COPY'):c.copy_state(p/'original',p/'new')
 def test_special_companion_or_existing_destination_blocks(self):
  with tempfile.TemporaryDirectory()as d:
   p=Path(d);self.snapshot(p/'original');(p/'original/link').symlink_to(p/'original/state.json')
   with self.assertRaises(c.Refusal):c.copy_state(p/'original',p/'new')
   self.assertFalse((p/'new').exists())
 def test_mutation_during_copy_blocks(self):
  with tempfile.TemporaryDirectory()as d:
   p=Path(d);self.snapshot(p/'original');real=c.shutil.copytree
   def mutate(*a,**kw):
    result=real(*a,**kw);(p/'original/state.json').write_text('{}');return result
   with patch.object(c.shutil,'copytree',side_effect=mutate):
    with self.assertRaises(c.Refusal):c.copy_state(p/'original',p/'new')
 def test_cleanup_only_owned_matching_child(self):
  child=Mock(pid=10);child.poll.return_value=None
  with patch.object(c,'identity',return_value={'start_ticks':20}):c.terminate_owned([(child,19)])
  child.terminate.assert_not_called()
  with patch.object(c,'identity',return_value={'start_ticks':20}):c.terminate_owned([(child,20)])
  child.terminate.assert_called_once()
 def test_mutable_environment_is_private(self):
  env=c.environment(Path('/token'),'test-only',Path('/private/new'),Path('/actual/venv/bin/python'))
  for name in ('TMPDIR','XDG_CACHE_HOME','XDG_CONFIG_HOME','XDG_DATA_HOME'):self.assertTrue(env[name].startswith('/private/new/'))
  self.assertEqual(env['HOME'],'/home/unreal');self.assertEqual(env['STREAMER_DIR'],'/home/unreal/.sub01-private/streamer')
  self.assertEqual(env['HOME_COMPUTER_ORIGIN'],'http://127.0.0.1:8838')
  self.assertTrue(env['PATH'].startswith('/actual/venv/bin:'))
 def test_no_provider_guard_or_broad_kill_entrypoint(self):
  text=P.read_text()
  for forbidden in ('guard_alive','--guard-pid','api.runpod','graphql','pgrep','killpg','SIGKILL'):self.assertNotIn(forbidden,text)
 def test_stop_is_startup_gate_not_service_lifetime(self):
  text=P.read_text();self.assertEqual(text.count("Path(args.stop_file).is_file()"),1)
  self.assertNotIn('stop_file',text[text.index('        while not stop:'):text.index('    finally:\n        terminate_owned')])
 def test_source_manifest_ignores_unconsumed_private_and_cache(self):
  with tempfile.TemporaryDirectory()as d:
   root=Path(d);(root/'music_curated.json').write_text('{}');(root/'used.py').write_text('x=1')
   for name in ('private','logs','__pycache__','.git'):
    (root/'tools'/name).mkdir(parents=True);(root/'tools'/name/'secret.py').write_text('not an input')
   (root/'.env').write_text('do not hash');(root/'old-state').mkdir();(root/'old-state'/'large').write_bytes(b'unused')
   result=c.source_manifest(root,'latest');self.assertEqual(set(result),{'used.py','music_curated.json'})
 def test_new_run_permissions_with_restrictive_umask(self):
  with tempfile.TemporaryDirectory()as d:
   target=Path(d)/'new';mask=os.umask(0o077)
   try:c.create_private_run(target,os.getuid(),os.getgid())
   finally:os.umask(mask)
   info=target.stat();self.assertEqual((info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode)),(os.getuid(),os.getgid(),0o700))
   source=target/'source';source.mkdir();script=source/'live_server.py';script.write_text('actual filesystem traversal')
   self.assertEqual(script.read_text(),'actual filesystem traversal')
   with self.assertRaises(FileExistsError):c.create_private_run(target,os.getuid(),os.getgid())
 def test_occupied_port_refuses_without_signalling(self):
  with patch.object(c.socket.socket,'bind',side_effect=OSError('occupied')):
   with self.assertRaises(c.Refusal):c.require_free_ports(False)
if __name__=='__main__':unittest.main()
