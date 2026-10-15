"""Loopback relay cannot grant remote sites the private house credentials."""
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/pixel_streaming'))
from local_native_proxy import create_app, local_request_allowed


@pytest.mark.parametrize('host,origin,method,ws,site,allowed',[
 ('localhost:8791','', 'GET',False,'none',True),
 ('localhost:8791','http://localhost:8791','POST',False,'same-origin',True),
 ('127.0.0.1:8791','http://127.0.0.1:8791','GET',True,'same-origin',True),
 ('localhost:8791','https://external.example','POST',False,'cross-site',False),
 ('localhost:8791','http://external.example','GET',True,'',False),
 ('external.example:8791','', 'GET',False,'',False),
 ('localhost:8791','', 'POST',False,'',False),
 ('localhost:8791','', 'GET',True,'',False),
 ('localhost:8791','http://localhost:8791','GET',False,'cross-site',False),
 ('localhost:8791','http://127.0.0.1:8791','POST',False,'same-origin',False),
 ('localhost:8791.evil.example','', 'GET',False,'',False),
])
def test_local_origin_and_dns_rebinding_boundaries(host,origin,method,ws,site,allowed):
 assert local_request_allowed(host,origin,8791,method,ws,site)is allowed


@pytest.mark.parametrize('base',[
 'http://dgtgepkz7h1zy5-8888.proxy.runpod.net',
 'https://external.example',
 'https://dgtgepkz7h1zy5-8888.proxy.runpod.net.evil.example',
 'https://name@dgtgepkz7h1zy5-8888.proxy.runpod.net',
 'https://dgtgepkz7h1zy5-8888.proxy.runpod.net/path',
])
def test_config_cannot_forward_private_credentials_to_another_target(base):
 with pytest.raises(ValueError,match='private Runpod origin'):
  create_app(base,'test-credential-never-sent',8791)
