"""Byte-preserved remainder for ONLY two generated picture backings in batch165."""
import copy
import hashlib
import json
import struct
from pathlib import Path

SOURCE_SHA='9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b'
BOUNDS=[[[1.33,2.83,-3.9025],[2.67,4.67,-3.8675]],
        [[-2.67,4.33,-3.8975],[-1.73,5.57,-3.8625]]]


def read(raw):
    length,kind=struct.unpack_from('<II',raw,12)
    if raw[:4]!=b'glTF' or kind!=0x4e4f534a:raise ValueError('GLB2 required')
    doc=json.loads(raw[20:20+length]);size,kind=struct.unpack_from('<II',raw,20+length)
    if kind!=0x004e4942:raise ValueError('GLB binary required')
    return doc,raw[28+length:28+length+size]


def elements(doc,blob,index):
    a=doc['accessors'][index];v=doc['bufferViews'][a['bufferView']]
    if a.get('sparse'):raise ValueError('Unexpected sparse source')
    fmt='<'+{5121:'B',5123:'H',5125:'I',5126:'f'}[a['componentType']]*{'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4}[a['type']]
    size=struct.calcsize(fmt);start=v.get('byteOffset',0)+a.get('byteOffset',0);step=v.get('byteStride',size)
    return [blob[start+i*step:start+i*step+size] for i in range(a['count'])],fmt


def prepare(source,output):
    raw=Path(source).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=SOURCE_SHA:raise ValueError('Exact source955 required')
    doc,blob=read(raw);node=doc['nodes'][165]
    if node.get('name')!='house-static-71' or node.get('mesh')!=124 or any(k in node for k in ('matrix','translation','rotation','scale')) or any(165 in n.get('children',[]) for n in doc['nodes']):raise ValueError('Exact root batch165 identity required')
    primitives=doc['meshes'][124]['primitives']
    if len(primitives)!=1 or primitives[0].get('material')!=5:raise ValueError('Exact single Material5 primitive required')
    p=primitives[0];raw_pos,fmt=elements(doc,blob,p['attributes']['POSITION']);pos=[struct.unpack(fmt,v) for v in raw_pos]
    raw_ids,fmt=elements(doc,blob,p['indices']);ids=[struct.unpack(fmt,v)[0] for v in raw_ids]
    if len(ids)!=3600:raise ValueError('Exact1200 source triangle batch required')
    for part,want in enumerate(BOUNDS):
        points=[pos[i]for i in ids[part*900:(part+1)*900]]
        bounds=[[min(v[a]for v in points)for a in range(3)],[max(v[a]for v in points)for a in range(3)]]
        if max(abs(a-b)for x,y in zip(bounds,want)for a,b in zip(x,y))>1e-6:raise ValueError('Reviewed box component bounds differ')
        if any(not all(want[0][a]-1e-6<=v[a]<=want[1][a]+1e-6 for a in range(3))for v in points):raise ValueError('Box selection escaped reviewed bounds')
    retained=ids[1800:];vertices=sorted(set(retained));mapping={v:i for i,v in enumerate(vertices)}
    result={'asset':{'version':'2.0','generator':'Exact original955 selected attribute bytes; no Blender re-export'},'scene':0,'scenes':[{'nodes':[0]}],
            'nodes':[{'name':'SUB01_FrameBackingRemainder_165_600','mesh':0}],
            'meshes':[{'name':'SUB01_FrameBackingRemainder_165_600','primitives':[]}],
            'materials':[{'name':'SUB01_RequireExistingMaterial5','pbrMetallicRoughness':{'baseColorFactor':[1,1,1,1]}}],'accessors':[],'bufferViews':[],'buffers':[]}
    # Geometry-only transfer: the importer MUST bind the exact existing
    # Material5, including its authored maps, rather than activate this placeholder.
    binary=bytearray();hashes={}
    def append(data,meta,target):
        binary.extend(b'\0'*(-len(binary)%4));offset=len(binary);binary.extend(data)
        view=len(result['bufferViews']);result['bufferViews'].append({'buffer':0,'byteOffset':offset,'byteLength':len(data),'target':target})
        a={k:copy.deepcopy(v)for k,v in meta.items()if k not in ('bufferView','byteOffset','sparse')};a['bufferView']=view
        result['accessors'].append(a);return len(result['accessors'])-1
    attributes={}
    for name,index in p['attributes'].items():
        values,fmt=elements(doc,blob,index);data=b''.join(values[i]for i in vertices);meta=copy.deepcopy(doc['accessors'][index]);meta['count']=len(vertices)
        if 'min'in meta or 'max'in meta:
            decoded=[struct.unpack(fmt,values[i])for i in vertices];meta['min']=[min(v[a]for v in decoded)for a in range(len(decoded[0]))];meta['max']=[max(v[a]for v in decoded)for a in range(len(decoded[0]))]
        attributes[name]=append(data,meta,34962);hashes[name]=hashlib.sha256(data).hexdigest()
    index_bytes=struct.pack('<'+'I'*len(retained),*(mapping[i]for i in retained))
    index=append(index_bytes,{'componentType':5125,'type':'SCALAR','count':len(retained),'min':[0],'max':[len(vertices)-1]},34963)
    result['meshes'][0]['primitives']=[{'attributes':attributes,'indices':index,'material':0,'mode':4}]
    result['buffers']=[{'byteLength':len(binary)}];text=json.dumps(result,separators=(',',':')).encode();text+=b' '*(-len(text)%4);binary.extend(b'\0'*(-len(binary)%4))
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    encoded=struct.pack('<III',0x46546c67,2,28+len(text)+len(binary))+struct.pack('<II',len(text),0x4e4f534a)+text+struct.pack('<II',len(binary),0x004e4942)+binary
    # Independently read the written accessors and compare every retained corner.
    rd,rb=read(encoded);rp=rd['meshes'][0]['primitives'][0];ri,rf=elements(rd,rb,rp['indices']);ri=[struct.unpack(rf,v)[0]for v in ri]
    for name,old in p['attributes'].items():
        expected,_=elements(doc,blob,old);actual,_=elements(rd,rb,rp['attributes'][name])
        if [expected[i]for i in retained]!=[actual[i]for i in ri]:raise ValueError('Retained triangle corner attributes changed '+name)
    output.write_bytes(encoded)
    proof={'schema':'sub01.frame-backing-remainder.v1','source_sha256':SOURCE_SHA,'output_sha256':hashlib.sha256(encoded).hexdigest(),
           'source_node':165,'source_mesh':124,'source_material':5,'source_triangles':1200,'removed_triangles':list(range(600)),
           'preserved_triangles':list(range(600,1200)),'preserved_triangle_count':600,'preserved_vertex_count':len(vertices),
           'removed_box_bounds_source_m':BOUNDS,'exact_retained_corner_attribute_bytes':True,'retained_attribute_sha256':hashes,
           'native_material_rebind_required':'/Game/Sub01Home/ImportedScene/full-home/Materials/Material_5.Material_5',
           'original_material_json_sha256':hashlib.sha256(json.dumps(doc['materials'][5],sort_keys=True).encode()).hexdigest(),
           'geometry_scope':'ONLY two home.js877/878 frame backings removed; door label frame and bedside darkwood retained','native_imported':False}
    output.with_suffix('.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof
