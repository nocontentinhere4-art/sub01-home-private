import asyncio,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from aiohttp.test_utils import TestClient,TestServer
from relay import create_app
PNG=b'\x89PNG\r\n\x1a\n'
class Response:
 def __init__(self,status=200,data=PNG,gate=None):self.status=status;self.content_type='image/png';self.data=data;self.gate=gate;self.content=self
 async def __aenter__(self):return self
 async def __aexit__(self,*a):pass
 async def iter_chunked(self,size):
  if self.gate:await self.gate.wait()
  for i in range(0,len(self.data),size):yield self.data[i:i+size]
class ScreenTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.tmp=tempfile.TemporaryDirectory();p=Path(self.tmp.name);(p/'token').write_text('private-test-token')
  self.client=TestClient(TestServer(create_app(p,p/'STOP',p/'token')));await self.client.start_server()
 async def asyncTearDown(self):await self.client.close();self.tmp.cleanup()
 def upstream(self,response):
  class Client:
   async def __aenter__(self):return self
   async def __aexit__(self,*a):pass
   def get(c,url,**kw):
    self.assertEqual(url,'http://127.0.0.1:8838/pc/frame.png');self.assertFalse(kw['allow_redirects']);self.assertEqual(kw['headers'],{'X-Admin-Token':'private-test-token'});return response
  return patch('relay.aiohttp.ClientSession',Client)
 async def test_png_no_token_or_cache(self):
  with self.upstream(Response()):
   r=await self.client.get('/screen.png');self.assertEqual(r.status,200);self.assertEqual(await r.read(),PNG);self.assertEqual(r.headers['Cache-Control'],'no-store');self.assertNotIn('private-test-token',str(r.headers))
 async def test_privacy_redirect_bad_image_and_chunked_oversize(self):
  for i,response in enumerate([Response(status=409),Response(status=302),Response(data=b'bad'),Response(data=PNG+b'x'*(4*1024*1024))]):
   with self.upstream(response):
    r=await self.client.get('/screen.png',headers={'CF-Connecting-IP':str(i)});self.assertEqual(r.status,503);self.assertEqual(r.headers['Cache-Control'],'no-store');self.assertEqual(await r.text(),'Unavailable')
 async def test_single_flight_no_stale_fallback(self):
  gate=asyncio.Event()
  with self.upstream(Response(gate=gate)):
   first=asyncio.create_task(self.client.get('/screen.png',headers={'CF-Connecting-IP':'a'}));await asyncio.sleep(.05)
   second=asyncio.create_task(self.client.get('/screen.png',headers={'CF-Connecting-IP':'b'}));await asyncio.sleep(.05);gate.set();self.assertEqual((await first).status,200);self.assertEqual((await second).status,200)
 async def test_no_generic_proxy(self):
  self.assertEqual((await self.client.get('/screen.png?url=http://evil.example')).status,404)
  self.assertEqual((await self.client.post('/screen.png')).status,405)
if __name__=='__main__':unittest.main()
