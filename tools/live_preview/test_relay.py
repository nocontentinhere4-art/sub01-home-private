import tempfile,unittest
from pathlib import Path
from aiohttp.test_utils import TestClient,TestServer
from relay import create_app,ORIGIN
class RelayTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.seg='sub01-20261026-233000-123.ts'
  (self.root/self.seg).write_bytes(b'media')
  (self.root/'live.m3u8').write_text('#EXTM3U\n#EXTINF:2,\n'+self.seg+'\n')
  self.client=TestClient(TestServer(create_app(self.root,self.root/'STOP')));await self.client.start_server()
 async def asyncTearDown(self):await self.client.close();self.tmp.cleanup()
 async def test_current_playlist_and_segment(self):
  for name in ['live.m3u8',self.seg]:
   r=await self.client.get('/hls/'+name,headers={'Origin':ORIGIN});self.assertEqual(r.status,200);self.assertEqual(r.headers['Access-Control-Allow-Origin'],ORIGIN)
 async def test_default_deny(self):
  for path in ['/operator','/pc/state','/lease','/hls/secret.json','/hls/%2e%2e%2fsecret.ts']:
   self.assertEqual((await self.client.get(path)).status,404)
  self.assertEqual((await self.client.head('/status')).status,405)
 async def test_origins_and_plain_text_only(self):
  self.assertEqual((await self.client.get('/status',headers={'Origin':'https://evil.example'})).status,403)
  self.assertEqual((await self.client.post('/chat',json={'role':'operator'},headers={'Origin':ORIGIN})).status,403)
  self.assertEqual((await self.client.post('/chat',data='hello')).status,403)
 async def test_traversal_in_playlist_and_symlinks(self):
  (self.root/'live.m3u8').write_text('#EXTM3U\n../secret.ts\n');self.assertEqual((await self.client.get('/hls/live.m3u8')).status,503)
  (self.root/'live.m3u8').write_text('#EXTM3U\n'+self.seg+'\n');(self.root/self.seg).unlink();(self.root/self.seg).symlink_to('/etc/passwd')
  self.assertEqual((await self.client.get('/hls/'+self.seg)).status,404)
 async def test_status_pause_and_body_limit(self):
  (self.root/'STOP').touch();r=await self.client.get('/status');self.assertEqual((await r.json())['agent'],'paused')
  r=await self.client.post('/chat',data='x'*3000,headers={'Origin':ORIGIN,'Content-Type':'text/plain'});self.assertEqual(r.status,413)
if __name__=='__main__':unittest.main()
