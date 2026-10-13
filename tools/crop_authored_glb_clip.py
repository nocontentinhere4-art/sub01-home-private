"""Crop an owned animation-only float-key GLB at existing captured sample times.
No interpolation, reposing, retiming, mirrored tracks, or finger modifications.
"""
import json, struct, pathlib, sys, hashlib
src, dest, start, end = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4])
raw=pathlib.Path(src).read_bytes(); size=struct.unpack_from('<I',raw,12)[0]
doc=json.loads(raw[20:20+size]); offset=20+size
assert struct.unpack_from('<I',raw,offset+4)[0]==0x004e4942
binary=raw[offset+8:]; assert not doc.get('meshes') and not doc.get('skins')
def read_accessor(index):
 a=doc['accessors'][index];v=doc['bufferViews'][a['bufferView']]
 assert a['componentType']==5126 and not a.get('sparse') and not v.get('extensions')
 n={'SCALAR':1,'VEC3':3,'VEC4':4}[a['type']];stride=v.get('byteStride',n*4);pos=v.get('byteOffset',0)+a.get('byteOffset',0)
 return [list(struct.unpack_from('<'+'f'*n,binary,pos+i*stride))for i in range(a['count'])]
new_binary=bytearray();views=[];accessors=[]
def append(values,kind):
 pos=len(new_binary)
 for value in values:new_binary.extend(struct.pack('<'+'f'*len(value),*value))
 views.append({'buffer':0,'byteOffset':pos,'byteLength':len(new_binary)-pos})
 a={'bufferView':len(views)-1,'componentType':5126,'count':len(values),'type':kind}
 if kind=='SCALAR':a.update(min=[values[0][0]],max=[values[-1][0]])
 accessors.append(a);return len(accessors)-1
animation=doc['animations'][0]; counts=[]
for sampler in animation['samplers']:
 times=read_accessor(sampler['input']);values=read_accessor(sampler['output']);assert len(times)==len(values)
 keep=[i for i,t in enumerate(times)if start-0.0001<=t[0]<=end+0.0001]
 assert keep and abs(times[keep[0]][0]-start)<.0001 and abs(times[keep[-1]][0]-end)<.0001,'Crop boundaries must be actual captured frame times'
 actual_start=times[keep[0]][0]
 output_type=doc['accessors'][sampler['output']]['type']
 sampler['input']=append([[times[i][0]-actual_start]for i in keep],'SCALAR')
 sampler['output']=append([values[i]for i in keep],output_type);counts.append(len(keep))
animation['name']='AuthoredBimanualTyping_3to8'
doc['animations']=[animation];doc['accessors']=accessors;doc['bufferViews']=views;doc['buffers']=[{'byteLength':len(new_binary)}]
doc.pop('extensionsUsed',None);doc.pop('extensionsRequired',None)
text=json.dumps(doc,separators=(',',':')).encode();text+=b' '*((-len(text))%4);new_binary+=b'\0'*((-len(new_binary))%4)
out=struct.pack('<III',0x46546c67,2,28+len(text)+len(new_binary))+struct.pack('<II',len(text),0x4e4f534a)+text+struct.pack('<II',len(new_binary),0x004e4942)+new_binary
pathlib.Path(dest).write_bytes(out)
audit={'privateOnly':True,'source':src,'sourceSHA256':hashlib.sha256(raw).hexdigest(),'outputSHA256':hashlib.sha256(out).hexdigest(),'sourceRangeSeconds':[start,end],'capturedSamplesPerTrack':counts,'authoredValuesPreservedExactly':True,'proceduralMotionAdded':False,'contactVisualAccepted':False,'scope':'Actual contiguous bimanual finger-active segment; contact placement remains unreviewed'}
pathlib.Path(dest+'.audit.json').write_text(json.dumps(audit,indent=2)+'\n');print(json.dumps({k:v for k,v in audit.items()if k!='capturedSamplesPerTrack'}))
