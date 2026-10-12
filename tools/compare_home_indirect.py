"""Compare unfiltered linear EXR bake detail inside smooth atlas faces.
Blender --background --python this_file -- atlas.glb before.exr after.exr result.json
Neighbor statistics never sample across atlas chart boundaries. They are a
spatial noise proxy, not proof of ground-truth convergence from two sample counts.
"""
import sys,json,struct
from pathlib import Path
import bpy
import numpy as np
atlas,before,after,output=map(Path,sys.argv[sys.argv.index('--')+1:])
raw=atlas.read_bytes();length=int.from_bytes(raw[12:16],'little');meta=json.loads(raw[20:20+length]);blob=raw[28+length:]
w,h=meta['extras']['width'],meta['extras']['height']
components={'SCALAR':1,'VEC2':2,'VEC3':3};types={5126:'<f4',5125:'<u4',5123:'<u2'}
def read(index):
 a=meta['accessors'][index];v=meta['bufferViews'][a['bufferView']];d=np.dtype(types[a['componentType']]);n=components[a['type']]
 return np.ndarray((a['count'],n),d,buffer=blob,offset=(v.get('byteOffset') or 0)+(a.get('byteOffset')or 0),strides=(v.get('byteStride')or d.itemsize*n,d.itemsize)).copy()
def exr(path):
 image=bpy.data.images.load(str(path),check_existing=False);assert tuple(image.size)==(w,h)
 pixels=np.empty(len(image.pixels),np.float32);image.pixels.foreach_get(pixels)
 rgb=pixels.reshape(h,w,4)[:,:,:3];assert np.isfinite(rgb).all()and rgb.min()>=0
 return rgb@np.array([.2126,.7152,.0722],np.float32)
regions={'loft_soffit':np.zeros((h,w),bool),'walls':np.zeros((h,w),bool)}
faces={key:0 for key in regions}
for mesh in meta['meshes']:
 p=mesh['primitives'][0];a=p['attributes'];positions=read(a['POSITION']);normals=read(a['NORMAL']);uv=read(a['TEXCOORD_1'])*[w,h]
 for indices in read(p['indices']).reshape(-1,3):
  xyz=positions[indices];normal=normals[indices].mean(axis=0);area=np.linalg.norm(np.cross(xyz[1]-xyz[0],xyz[2]-xyz[0]))/2
  if area<.25:continue
  y=xyz[:,1].mean()
  key='loft_soffit'if normal[1]<-.95 and 2.7<y<3.05 else 'walls'if abs(normal[1])<.05 and (abs(xyz[:,0].mean()-3.91)<.15 or abs(xyz[:,2].mean()+3.91)<.15)else None
  if key is None:continue
  triangle=uv[indices];lo=np.maximum(0,np.floor(triangle.min(axis=0)).astype(int));hi=np.minimum([w-1,h-1],np.ceil(triangle.max(axis=0)).astype(int))
  xs,ys=np.meshgrid(np.arange(lo[0],hi[0]+1)+.5,np.arange(lo[1],hi[1]+1)+.5)
  a,b,c=triangle;den=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1]);
  if abs(den)<1e-8:continue
  u=((b[1]-c[1])*(xs-c[0])+(c[0]-b[0])*(ys-c[1]))/den
  v=((c[1]-a[1])*(xs-c[0])+(a[0]-c[0])*(ys-c[1]))/den
  interior=(u>.025)&(v>.025)&(1-u-v>.025)
  regions[key][lo[1]:hi[1]+1,lo[0]:hi[0]+1]|=interior;faces[key]+=1
old,new=exr(before),exr(after)
result={'width':w,'height':h,'before':str(before),'after':str(after),'interpretation':'Unfiltered atlas-face interior neighbor residuals are a spatial-noise proxy. Two budgets do not establish absolute convergence; visual comparison still required.','regions':{}}
for key,mask in regions.items():
 safe=mask[1:-1,1:-1]&mask[:-2,1:-1]&mask[2:,1:-1]&mask[1:-1,:-2]&mask[1:-1,2:]
 assert safe.sum()>100,key+' region insufficient'
 stats={}
 for label,values in [('before',old),('after',new)]:
  centres=values[1:-1,1:-1];residual=centres-(values[:-2,1:-1]+values[2:,1:-1]+values[1:-1,:-2]+values[1:-1,2:])/4
  v=centres[safe];r=residual[safe]
  stats[label]={'mean_linear_luminance':float(v.mean()),'neighbor_residual_rms':float(np.sqrt(np.mean(r*r))),'neighbor_residual_median_abs':float(np.median(abs(r))),'neighbor_residual_p95_abs':float(np.percentile(abs(r),95))}
 stats['pixels']=int(safe.sum());stats['faces']=faces[key];stats['rms_ratio_after_before']=stats['after']['neighbor_residual_rms']/max(1e-12,stats['before']['neighbor_residual_rms'])
 stats['change_rms']=float(np.sqrt(np.mean((new[1:-1,1:-1][safe]-old[1:-1,1:-1][safe])**2)));result['regions'][key]=stats
output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,indent=2)+'\n');print('COMPARE',json.dumps(result),flush=True)
