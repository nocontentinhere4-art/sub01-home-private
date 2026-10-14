"""Private GPU launch configuration; no browser/display/game is launched."""
import os
from unittest.mock import patch
import pytest
from home_minecraft import minecraft_browser_launch_options

def test_default_preserves_headless_browser_without_x_credentials():
 with patch.dict(os.environ,{},clear=True):
  assert minecraft_browser_launch_options()=={'headless':True}

def test_opt_in_uses_private_same_owner_authority_without_reading_cookie(tmp_path):
 authority=tmp_path/'authority';authority.write_bytes(b'fixture cookie must never be parsed');authority.chmod(0o600)
 with patch.dict(os.environ,{'SUB01_MC_HARDWARE_WEBGL':'1','SUB01_MC_XAUTHORITY':str(authority)},clear=True):
  options=minecraft_browser_launch_options()
 assert options['env']['DISPLAY']==':99' and options['env']['XAUTHORITY']==str(authority)
 assert '--use-angle=gl' in options['args'] and '--enable-gpu' in options['args']
 assert options['ignore_default_args']==['--enable-unsafe-swiftshader']
 assert 'executable_path' not in options and 'user_data_dir' not in options

def test_rejects_public_display_and_exposed_authority(tmp_path):
 authority=tmp_path/'authority';authority.touch();authority.chmod(0o644)
 with patch.dict(os.environ,{'SUB01_MC_HARDWARE_WEBGL':'1','SUB01_MC_XAUTHORITY':str(authority)},clear=True):
  with pytest.raises(ValueError):minecraft_browser_launch_options()
  authority.chmod(0o600);os.environ['SUB01_MC_DISPLAY']='remote.example:0'
  with pytest.raises(ValueError):minecraft_browser_launch_options()
  os.environ['SUB01_MC_DISPLAY']=':99'
  with patch('home_minecraft.os.getuid',return_value=authority.stat().st_uid+1):
   with pytest.raises(ValueError):minecraft_browser_launch_options()
