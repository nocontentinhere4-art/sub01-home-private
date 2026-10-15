"""Independent preservation check for the actual licensed captured-owner review."""
import json, struct, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def glb(p):
 raw=p.read_bytes();d=b=None;o=12
 while o<len(raw):
  n,k=struct.unpack_from('<II',raw,o);chunk=raw[o+8:o+8+n]
  if k==0x4e4f534a:d=json.loads(chunk)
  elif k==0x004e4942:b=chunk
  o+=8+n
 return d,b

def accessor(d,b,index):
 a=d['accessors'][index];v=d['bufferViews'][a['bufferView']];size={'SCALAR':1,'VEC3':3,'VEC4':4}[a['type']];assert a['componentType']==5126
 return [struct.unpack_from('<'+'f'*size,b,v.get('byteOffset',0)+a.get('byteOffset',0)+i*v.get('byteStride',size*4))for i in range(a['count'])]
def test_actual_capture_tracks_and_owner_mesh_are_exact(tmp_path):
 owner=ROOT/'web/room/char_mixamo.glb';capture=ROOT/'web/house/assets/first-person/walking.glb';out=tmp_path/'canonical.glb'
 subprocess.run(['node',str(ROOT/'tools/bind_canonical_walk_owner.mjs'),str(owner),str(capture),str(out)],check=True,capture_output=True)
 od,ob=glb(owner);cd,cb=glb(capture);d,b=glb(out)
 assert b[:len(ob)]==ob
 for key in ['nodes','meshes','skins','materials','images','textures']:assert d.get(key)==od.get(key)
 source=cd['animations'][0];result=d['animations'][0];assert len(source['channels'])==len(result['channels'])==66
 for sc,tc in zip(source['channels'],result['channels']):
  assert sc['target']['path']==tc['target']['path']
  assert cd['nodes'][sc['target']['node']]['name']==d['nodes'][tc['target']['node']]['name']
  ss=source['samplers'][sc['sampler']];ts=result['samplers'][tc['sampler']]
  assert ss.get('interpolation','LINEAR')==ts.get('interpolation','LINEAR')
  for key in ['input','output']:assert accessor(cd,cb,ss[key])==accessor(d,b,ts[key])
