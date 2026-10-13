"""Extract existing licensed embedded PBR maps, full1K/lite512; no new assets."""
from pathlib import Path
import struct,json,io,hashlib
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'web/house/assets/haven-sofa/source.glb'
raw=SRC.read_bytes()
assert hashlib.sha256(raw).hexdigest()=='acad7fd3d9431929c303b1ae5cd476d7a108ce352a99ddf40e4e78ea7b9f2643'
n=struct.unpack_from('<I',raw,12)[0];j=json.loads(raw[20:20+n]);blob=raw[28+n:]
files=[]
for image in j['images']:
 view=j['bufferViews'][image['bufferView']];data=blob[view.get('byteOffset',0):view.get('byteOffset',0)+view['byteLength']]
 decoded=Image.open(io.BytesIO(data)).convert('RGB');name=image['name']
 for quality,edge in [('full',1024),('lite',512)]:
  out=ROOT/'web/house/assets'/('' if quality=='full' else 'lite')/'haven-sofa/maps';out.mkdir(parents=True,exist_ok=True)
  resized=decoded.copy();resized.thumbnail((edge,edge),Image.Resampling.LANCZOS)
  path=out/(name+'.jpg');resized.save(path,quality=97 if name.endswith('normal') else 94,subsampling=0)
  files.append({'file':str(path.relative_to(ROOT/'web/house/assets')),'dimensions':list(resized.size),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size})
(ROOT/'web/house/assets/haven-sofa/texture-manifest.json').write_text(json.dumps({'license':'CC0-1.0','source':'https://www.innerscene.com/tools/library/3d-parts/haven-224-oatmeal-two-seat-sofa-40262c27','source_sha256':hashlib.sha256(raw).hexdigest(),'transformation':'PNG decoded to RGB JPEG without color grading; retained packed roughness green channel. Full1024, lite512 Lanczos.','files':files},indent=2))
print('HAVEN_TEXTURES',sum(x['bytes'] for x in files),'bytes across full/lite')
