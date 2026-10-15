"""Bounded offline seam correction; requires subsequent full-skin and world-travel audits."""
import argparse, hashlib, json, math, struct
from pathlib import Path


def slerp(a, b, t):
    dot=sum(x*y for x,y in zip(a,b))
    if dot<0:b=[-v for v in b];dot=-dot
    if dot>.9995:q=[x+t*(y-x)for x,y in zip(a,b)]
    else:
        theta=math.acos(max(-1,min(1,dot)));s=math.sin(theta)
        q=[(math.sin((1-t)*theta)*x+math.sin(t*theta)*y)/s for x,y in zip(a,b)]
    length=math.sqrt(sum(v*v for v in q));return [v/length for v in q]


def angle(a,b):
    return math.degrees(2*math.acos(min(1,abs(sum(x*y for x,y in zip(a,b))))))


def close(source, output, expected, window=8, max_rotation_deg=5):
    raw=source.read_bytes();assert hashlib.sha256(raw).hexdigest()==expected
    n=struct.unpack_from('<I',raw,12)[0];doc=json.loads(raw[20:20+n]);length,kind=struct.unpack_from('<II',raw,20+n);assert kind==0x004e4942
    binary=bytearray(raw[28+n:28+n+length]);original=bytes(binary);changes=[]
    for channel in doc['animations'][0]['channels']:
        sampler=doc['animations'][0]['samplers'][channel['sampler']];a=doc['accessors'][sampler['output']];v=doc['bufferViews'][a['bufferView']]
        assert a['componentType']==5126 and not v.get('byteStride')
        size={'VEC3':3,'VEC4':4}[a['type']];start=v.get('byteOffset',0)+a.get('byteOffset',0);count=a['count'];assert count>2*window
        values=[list(struct.unpack_from('<'+'f'*size,binary,start+i*size*4))for i in range(count)]
        edges=[values[0][:],values[-1][:]]
        path=channel['target']['path'];name=doc['nodes'][channel['target']['node']]['name']
        if path=='rotation':
            target=slerp(values[0],values[-1],.5);error=angle(values[0],values[-1]);assert error*.5<=max_rotation_deg,(name,error)
            # Distribute only near seam; retain the interior captured samples exactly.
            for i in range(window):
                w=1-i/(window-1);w=w*w*(3-2*w)
                for index in {i,count-1-i}:
                    edge=edges[0 if index<window else 1]
                    # Apply a bounded local endpoint correction by quaternion multiplication.
                    goal=slerp(edge,target,w);inv=[-edge[0],-edge[1],-edge[2],edge[3]]
                    def mul(a,b):
                        x,y,z,w=a;X,Y,Z,W=b;return [w*X+x*W+y*Z-z*Y,w*Y-x*Z+y*W+z*X,w*Z+x*Y-y*X+z*W,w*W-x*X-y*Y-z*Z]
                    values[index]=mul(mul(goal,inv),values[index])
            values[0]=target;values[-1]=target
            changes.append({'bone':name,'rotation_seam_before_deg':error,'max_endpoint_correction_deg':error/2})
        elif path=='translation':
            assert 'Hips' in name or values[0]==values[-1], 'Non-Hips translation cannot change'
            if 'Hips' in name:
                assert abs(values[0][0]-values[-1][0])<1e-6 and abs(values[0][2]-values[-1][2])<1e-6
                target=(values[0][1]+values[-1][1])/2
                # Rig is centimetres; bound world pelvis seam correction to 5mm.
                assert abs(values[0][1]-target)*.01<=.005
                for i in range(window):
                    w=1-i/(window-1);w=w*w*(3-2*w)
                    for index in {i,count-1-i}:values[index][1]+=w*(target-edges[0 if index<window else 1][1])
                values[0][1]=target;values[-1][1]=target
        else:raise AssertionError('Unexpected animation channel')
        for i,value in enumerate(values):struct.pack_into('<'+'f'*size,binary,start+i*size*4,*value)
    # Only existing animation outputs are writable; geometry and node graph are untouched.
    spans=[]
    for channel in doc['animations'][0]['channels']:
        a=doc['accessors'][doc['animations'][0]['samplers'][channel['sampler']]['output']];v=doc['bufferViews'][a['bufferView']];size={'VEC3':3,'VEC4':4}[a['type']];start=v.get('byteOffset',0)+a.get('byteOffset',0);spans.append((start,start+a['count']*size*4))
    at=0
    for lo,hi in sorted(spans):assert binary[at:lo]==original[at:lo];at=hi
    assert binary[at:]==original[at:]
    result=bytearray(raw);result[28+n:28+n+length]=binary;output.write_bytes(result)
    report={'schema':'sub01.source-only-bounded-loop-seam.v1','source_sha256':expected,'output_sha256':hashlib.sha256(result).hexdigest(),'boundary_window_frames':window,'rotation_changes':changes,'original_geometry_and_non_animation_bytes_exact':True,'fixed_nonhips_translations':True,'full_skin_contact_reprojection_required':True,'velocity_seam_accepted':False,'world_horizontal_contact_accepted':False,'native_changed':False}
    Path(str(output)+'.json').write_text(json.dumps(report,indent=2)+'\n');return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('output',type=Path);p.add_argument('sha');a=p.parse_args();print(json.dumps(close(a.source,a.output,a.sha)))
