import base64,json,unittest
from unittest.mock import Mock
from aiohttp import web
import local_bridge as l,remote_relay as r
class Tests(unittest.TestCase):
 def test_routes_host_origin_and_nonce(self):
  b=object.__new__(l.Bridge);b.port=18838;b.origin='http://127.0.0.1:18838';b.nonce='abc'
  self.assertEqual(b.route('GET','/abc/operator','127.0.0.1:18838',None),'/operator')
  self.assertEqual(b.route('POST','/abc/operator/input','127.0.0.1:18838',b.origin),'/operator/input')
  for method,path,host,origin in [('GET','/abc/operator','evil',None),('POST','/abc/operator/input','127.0.0.1:18838',None),('GET','/abc/operator','127.0.0.1:18838','http://evil'),('GET','/bad/operator','127.0.0.1:18838',None),('GET','/abc/../../secret','127.0.0.1:18838',None)]:
   with self.assertRaises(web.HTTPException):b.route(method,path,host,origin)
 def test_remote_fixed_target_token_and_hop_headers(self):
  response=Mock(status=200);response.read.return_value=b'jpeg';response.getheaders.return_value=[('Content-Type','image/jpeg'),('Connection','keep-alive'),('Set-Cookie','secret')]
  conn=Mock();conn.getresponse.return_value=response;factory=Mock(return_value=conn)
  result=r.relay({'method':'GET','path':'/operator/frame.jpg','body':''},'existing-secret',factory)
  factory.assert_called_once_with('127.0.0.1',8838,timeout=8);self.assertEqual(conn.request.call_args.kwargs['headers']['X-Admin-Token'],'existing-secret');self.assertEqual(result['headers'],{'Content-Type':'image/jpeg'});conn.close.assert_called_once()
 def test_remote_routes_and_bounds(self):
  for path in ['http://evil','/admin','/operator?redirect=evil']:
   with self.assertRaises(ValueError):r.relay({'method':'GET','path':path},'secret')
  with self.assertRaises(ValueError):r.relay({'method':'POST','path':'/operator/input','body':base64.b64encode(b'x'*(r.MAX_REQUEST+1)).decode()},'secret')
 def test_no_post_retry_and_close_on_error(self):
  conn=Mock();conn.request.side_effect=OSError('lost');factory=Mock(return_value=conn)
  with self.assertRaises(OSError):r.relay({'method':'POST','path':'/operator/input','body':''},'secret',factory)
  conn.request.assert_called_once();conn.close.assert_called_once()
 def test_redirect_rejected_without_follow(self):
  response=Mock(status=302);conn=Mock();conn.getresponse.return_value=response;factory=Mock(return_value=conn)
  with self.assertRaises(ValueError):r.relay({'method':'GET','path':'/operator'},'secret',factory)
  conn.request.assert_called_once();response.read.assert_not_called();conn.close.assert_called_once()
class AsyncTests(unittest.IsolatedAsyncioTestCase):
 async def test_busy_fails_before_read_or_send(self):
  import asyncio
  b=object.__new__(l.Bridge);b.queued=1;b.lock=asyncio.Lock();req=Mock()
  with self.assertRaises(web.HTTPTooManyRequests):await b.handle(req)
  req.read.assert_not_called()
if __name__=='__main__':unittest.main()
