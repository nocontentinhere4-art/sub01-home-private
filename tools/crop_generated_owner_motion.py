"""Crop actual body keys at existing samples; preserve every original asset byte."""
import argparse, copy, hashlib, json, struct
from pathlib import Path

def crop(source, output, first, last, fps, expected):
    raw=source.read_bytes();assert hashlib.sha256(raw).hexdigest()==expected
    size=struct.unpack_from('<I',raw,12)[0];doc=json.loads(raw[20:20+size]);at=20+size;length,kind=struct.unpack_from('<II',raw,at);assert kind==0x004e4942
    binary=raw[at+8:at+8+length];original=copy.deepcopy(doc);parts=[binary];offset=len(binary)
    def read(index):
        a=doc['accessors'][index];v=doc['bufferViews'][a['bufferView']];assert a['componentType']==5126 and not a.get('sparse') and not v.get('extensions')
        n={'SCALAR':1,'VEC3':3,'VEC4':4}[a['type']];assert not v.get('byteStride');start=v.get('byteOffset',0)+a.get('byteOffset',0)
        return a,binary[start:start+a['count']*n*4],n
    def append(data,n,kind,minmax=None):
        nonlocal offset
        view=len(doc['bufferViews']);doc['bufferViews'].append({'buffer':0,'byteOffset':offset,'byteLength':len(data)});parts.append(data);offset+=len(data)
        index=len(doc['accessors']);a={'bufferView':view,'componentType':5126,'count':len(data)//(4*n),'type':kind}
        if minmax:a.update(min=[minmax[0]],max=[minmax[1]])
        doc['accessors'].append(a);return index
    assert 0<=first<last
    for sampler in doc['animations'][0]['samplers']:
        _,t,_=read(sampler['input']);values=struct.unpack('<'+'f'*(len(t)//4),t);assert last<len(values)
        assert all(abs(v-i/fps)<1e-5 for i,v in enumerate(values))
        a,v,n=read(sampler['output']);assert a['count']==len(values)
        times=[values[i]-values[first] for i in range(first,last+1)]
        sampler['input']=append(struct.pack('<'+'f'*len(times),*times),1,'SCALAR',[0,times[-1]])
        sampler['output']=append(v[first*n*4:(last+1)*n*4],n,a['type'])
    doc['animations'][0]['extras']={**doc['animations'][0].get('extras',{}),'originalFrameRange':[first,last],'originalFps':fps,'nativeAccepted':False}
    doc['buffers'][0]['byteLength']=offset
    b=b''.join(parts);assert b[:len(binary)]==binary
    for key in ['nodes','skins','meshes','images','textures','materials']:assert doc.get(key)==original.get(key)
    text=json.dumps(doc,separators=(',',':')).encode();text+=b' '*(-len(text)%4)
    output.write_bytes(struct.pack('<IIIII',0x46546c67,2,28+len(text)+len(b),len(text),0x4e4f534a)+text+struct.pack('<II',len(b),0x004e4942)+b)
    report={'schema':'sub01.generated-owner-exact-key-crop.v1','source_sha256':expected,'output_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'original_frame_range':[first,last],'fps':fps,'frames':last-first+1,'duration_s':(last-first)/fps,'all_original_binary_preserved':True,'retained_motion_values_byte_exact':True,'original_owner_nodes_skin_meshes_images_materials_exact':True,'no_interpolation_or_retime':True,'native_changed':False,'visual_accepted':False}
    Path(str(output)+'.json').write_text(json.dumps(report,indent=2)+'\n');return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('output',type=Path);p.add_argument('first',type=int);p.add_argument('last',type=int);p.add_argument('fps',type=int);p.add_argument('expected_sha256');a=p.parse_args();print(json.dumps(crop(a.source,a.output,a.first,a.last,a.fps,a.expected_sha256)))
