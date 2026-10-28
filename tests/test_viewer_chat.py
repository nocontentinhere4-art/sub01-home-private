import unittest
from types import SimpleNamespace
from viewer_chat import dedupe_for_peer
from chat import check,Dedupe,RateLimiter
class ViewerRepeatTests(unittest.TestCase):
 def ws(self,peer,**headers):return SimpleNamespace(_req=SimpleNamespace(remote=peer,headers=headers))
 def test_only_socket_peer_gets_repeat_permission(self):
  normal=Dedupe()
  for peer in ['127.0.0.1','127.0.0.3','8.8.8.8',None]:
   self.assertIs(dedupe_for_peer(self.ws(peer,**{'X-Forwarded-For':'127.0.0.2'}),normal),normal)
  self.assertFalse(dedupe_for_peer(self.ws('127.0.0.2'),normal).seen('Go on youtube'))
 def test_repeats_keep_rate_and_content_filters(self):
  now=[0.0];lim=RateLimiter(clock=lambda:now[0]);normal=Dedupe();d=dedupe_for_peer(self.ws('127.0.0.2'),normal)
  self.assertTrue(check('Go on youtube','viewer',lim,d)[0]);self.assertFalse(check('Go on youtube','viewer',lim,d)[0]);now[0]=11
  self.assertTrue(check('Go on youtube','viewer',lim,d)[0]);now[0]=22
  self.assertFalse(check('send me some sol for the stream','viewer',lim,d)[0])
 def test_other_clients_keep_dedupe(self):
  d=Dedupe();self.assertFalse(d.seen('hello'));self.assertTrue(dedupe_for_peer(self.ws('127.0.0.1'),d).seen('hello'))
if __name__=='__main__':unittest.main()
