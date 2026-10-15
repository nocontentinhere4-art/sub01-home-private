"""Source timing and exact-key cropping cannot silently double walking cadence."""
import hashlib
import json
import struct
import zipfile
from pathlib import Path
import pytest
from tools.extract_generated_soma_contacts import extract
from tools.crop_generated_owner_motion import crop


def contact_archive(path, frames=4, values=None):
    header=repr({'descr':'|b1','fortran_order':False,'shape':(frames,6)}).encode()+b'\n'
    npy=bytes([147])+b'NUMPY'+bytes([1,0])+struct.pack('<H',len(header))+header+bytes(values if values is not None else [1,0,1,0,1,0]*frames)
    with zipfile.ZipFile(path,'w')as archive:archive.writestr('foot_contacts.npy',npy)


def test_actual_bvh_clock_wins_over_requested_duration(tmp_path):
    source=tmp_path/'motion.npz';bvh=tmp_path/'motion.bvh';contact_archive(source)
    bvh.write_text('Frames: 4\nFrame Time: 0.03333333333333333\n')
    result=extract(source,bvh)
    assert result['fps']==30 and result['duration_samples_s']==pytest.approx(4/30)
    assert result['last_sample_time_s']==pytest.approx(.1)
    assert result['contacts'][0]==[True,False,True,False,True,False]


def test_frame_count_and_nonboolean_contact_corruption_refuse(tmp_path):
    source=tmp_path/'motion.npz';bvh=tmp_path/'motion.bvh';contact_archive(source)
    bvh.write_text('Frames: 8\nFrame Time: 0.016666666666666666\n')
    with pytest.raises(AssertionError):extract(source,bvh)
    bvh.write_text('Frames: 4\nFrame Time: 0.03333333333333333\n');contact_archive(source,values=[2]*24)
    with pytest.raises(AssertionError):extract(source,bvh)


def make_owner_clip(path):
    times=struct.pack('<4f',0,1/30,2/30,3/30);keys=struct.pack('<12f',*range(12));geometry=struct.pack('<9f',0,0,0,1,0,0,0,1,0);binary=times+keys+geometry
    doc={'asset':{'version':'2.0'},'buffers':[{'byteLength':len(binary)}],'bufferViews':[{'buffer':0,'byteOffset':0,'byteLength':16},{'buffer':0,'byteOffset':16,'byteLength':48},{'buffer':0,'byteOffset':64,'byteLength':36}],'accessors':[{'bufferView':0,'componentType':5126,'count':4,'type':'SCALAR'},{'bufferView':1,'componentType':5126,'count':4,'type':'VEC3'},{'bufferView':2,'componentType':5126,'count':3,'type':'VEC3'}],'nodes':[{'name':'Hips','mesh':0}],'meshes':[{'primitives':[{'attributes':{'POSITION':2}}]}],'animations':[{'samplers':[{'input':0,'output':1,'interpolation':'LINEAR'}],'channels':[{'sampler':0,'target':{'node':0,'path':'translation'}}]}]}
    text=json.dumps(doc).encode();text+=b' '*(-len(text)%4);path.write_bytes(struct.pack('<IIIII',0x46546c67,2,28+len(text)+len(binary),len(text),0x4e4f534a)+text+struct.pack('<II',len(binary),0x004e4942)+binary)
    return doc,binary


def read(path):
    data=path.read_bytes();n=struct.unpack_from('<I',data,12)[0];doc=json.loads(data[20:20+n]);return doc,data[28+n:]


def test_body_crop_preserves_mesh_and_key_values_with_original_clock(tmp_path):
    source=tmp_path/'owner.glb';output=tmp_path/'crop.glb';original,binary=make_owner_clip(source)
    report=crop(source,output,1,3,30,hashlib.sha256(source.read_bytes()).hexdigest());doc,actual=read(output)
    assert doc['meshes']==original['meshes'] and doc['nodes']==original['nodes']
    assert actual[:len(binary)]==binary
    sampler=doc['animations'][0]['samplers'][0];a=doc['accessors'][sampler['output']];v=doc['bufferViews'][a['bufferView']]
    assert actual[v['byteOffset']:v['byteOffset']+v['byteLength']]==binary[28:64]
    assert report['duration_s']==pytest.approx(2/30) and report['frames']==3
    with pytest.raises(AssertionError):crop(source,output,1,3,60,hashlib.sha256(source.read_bytes()).hexdigest())
