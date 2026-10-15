"""Portable low-saturation dyed linen maps from the original CC0 albedo only."""
import json,struct,hashlib,io
from pathlib import Path
import numpy as np
from PIL import Image
SOURCE=Path('/home/unreal/runtime-tools/gaming-haven-source.glb');ROOT=Path('/workspace/sub01-home-private/reference-gaming-lounge-r1/haven-palette-r2');ROOT.mkdir(parents=True,exist_ok=True)
b=SOURCE.read_bytes();assert hashlib.sha256(b).hexdigest()=='acad7fd3d9431929c303b1ae5cd476d7a108ce352a99ddf40e4e78ea7b9f2643';p=12;doc=blob=None
while p<len(b):
 n,k=struct.unpack_from('<II',b,p);data=b[p+8:p+8+n]
 if k==0x4e4f534a:doc=json.loads(data)
 elif k==0x004e4942:blob=data
 p+=n+8
m=next(m for m in doc['materials']if m['name']=='Oatmeal | interlaced natural linen');image=doc['images'][doc['textures'][m['pbrMetallicRoughness']['baseColorTexture']['index']]['source']];view=doc['bufferViews'][image['bufferView']];a=view.get('byteOffset',0);original=blob[a:a+view['byteLength']];im=Image.open(io.BytesIO(original)).convert('RGB');rgb=np.asarray(im,dtype=np.float64)/255
lin=lambda x:np.where(x<=.04045,x/12.92,((x+.055)/1.055)**2.4)
srgb=lambda x:np.where(x<=.0031308,x*12.92,1.055*np.power(x,1/2.4)-.055)
y=np.einsum('...i,i->...',lin(rgb),[.2126,.7152,.0722]);report={'schema':'sub01.source-linen-palette.v1','source_glb_sha256':hashlib.sha256(b).hexdigest(),'source_albedo_sha256':hashlib.sha256(original).hexdigest(),'normal_and_roughness_source_unchanged':True,'maps':{}}
for role,factor in [('Navy',(.07,.11,.17)),('Gray',(.80,.85,.92)),('Accent',(.04,.065,.11))]:
 dyed=np.clip(y[:,:,None]*factor,0,1);pixels=np.rint(np.clip(srgb(dyed),0,1)*255).astype('uint8');out=ROOT/(role.lower()+'-linen.png');Image.fromarray(pixels).save(out);actual=lin(pixels/255);report['maps'][role]={'path':str(out),'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'dye_linear_factor':factor,'sheen_linear_mean':np.mean(actual,axis=(0,1)).tolist(),'source_luminance_variation_preserved':True}
(ROOT/'palette.json').write_text(json.dumps(report,indent=2));print('PORTABLE_HAVEN_PALETTE_READY',flush=True)
