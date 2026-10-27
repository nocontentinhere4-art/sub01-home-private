import asyncio,io,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from aiohttp.test_utils import TestClient,TestServer
from PIL import Image
from relay import create_app
class Response:
 def __init__(self,status=200,data=b'',headers=None):self.status=status;self.content_type='image/png';self.data=data;self.headers=headers or {};self.content=self
 async def __aenter__(self):return self
 async def __aexit__(self,*a):pass
 async def iter_chunked(self,size):
  for i in range(0,len(self.data),size):yield self.data[i:i+size]
class ScreenJpgTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.tmp=tempfile.TemporaryDirectory();p=Path(self.tmp.name);(p/'token').write_text('private-test-token')
  output=io.BytesIO();Image.new('RGB',(1280,720),(20,40,60)).save(output,format='PNG');self.png=output.getvalue()
  self.calls=[]
  self.client=TestClient(TestServer(create_app(p,p/'STOP',p/'token')));await self.client.start_server()
 async def asyncTearDown(self):await self.client.close();self.tmp.cleanup()
 def upstream(self,*responses):
  class Client:
   async def __aenter__(self):return self
   async def __aexit__(self,*a):pass
   def get(c,url,**kw):
    self.assertEqual(url,'http://127.0.0.1:8838/pc/frame.png');self.assertFalse(kw['allow_redirects']);self.assertEqual(kw['headers']['X-Admin-Token'],'private-test-token')
    self.calls.append(kw['headers']);return responses[min(len(self.calls),len(responses))-1]   # the last one repeats
  return patch('relay.aiohttp.ClientSession',Client)
 async def test_jpeg_served_and_cached(self):
  with self.upstream(Response(data=self.png,headers={'ETag':'frame-1'})):
   first=await self.client.get('/screen.jpg');self.assertEqual(first.status,200);self.assertEqual(first.content_type,'image/jpeg');body=await first.read()
   second=await self.client.get('/screen.jpg');self.assertEqual(second.status,200);self.assertEqual(await second.read(),body)
  self.assertEqual(len(self.calls),1);self.assertTrue(body.startswith(b'\xff\xd8'))
  with Image.open(io.BytesIO(body)) as image:self.assertEqual(image.size,(960,540))
 async def test_304_reuses_cache(self):
  with self.upstream(Response(data=self.png,headers={'ETag':'frame-1'}),Response(status=304)):
   first=await self.client.get('/screen.jpg');body=await first.read();await asyncio.sleep(0.11)
   second=await self.client.get('/screen.jpg');self.assertEqual(second.status,200);self.assertEqual(await second.read(),body)
   third=await self.client.get('/screen.jpg');self.assertEqual(third.status,200);self.assertEqual(await third.read(),body)
  self.assertEqual(len(self.calls),2);self.assertEqual(self.calls[1]['If-None-Match'],'frame-1')
 async def test_privacy_drops_cache(self):
  with self.upstream(Response(data=self.png),Response(status=409),Response(status=409)):
   self.assertEqual((await self.client.get('/screen.jpg')).status,200);await asyncio.sleep(0.11)
   self.assertEqual((await self.client.get('/screen.jpg')).status,503)
   self.assertEqual((await self.client.get('/screen.jpg')).status,503)
  self.assertEqual(len(self.calls),3)
 async def test_query_string_not_found(self):
  r=await self.client.get('/screen.jpg?x=1');self.assertEqual(r.status,404);self.assertEqual(self.calls,[])
 async def test_all_budget_not_consumed(self):
  with self.upstream(Response(data=self.png)):
   for _ in range(120):self.assertEqual((await self.client.get('/screen.jpg')).status,200)
  self.assertEqual((await self.client.get('/status')).status,200)   # the 'all' budget is untouched
