"""Independent serialized portable PBR evidence for the private Haven candidate."""
import hashlib,json,struct
from pathlib import Path

def read(path):
    raw=Path(path).read_bytes(); size=struct.unpack_from('<I',raw,12)[0]
    return json.loads(raw[20:20+size]),raw[28+size:],hashlib.sha256(raw).hexdigest()

def image_hash(g,b,t):
    if t is None:return None
    image=g['images'][g['textures'][t['index']]['source']]
    view=g['bufferViews'][image['bufferView']];start=view.get('byteOffset',0)
    return hashlib.sha256(b[start:start+view['byteLength']]).hexdigest()

def prove(source,candidate):
    s,sb,sh=read(source);g,b,ch=read(candidate)
    assert sh=='acad7fd3d9431929c303b1ae5cd476d7a108ce352a99ddf40e4e78ea7b9f2643'
    linen=next(m for m in s['materials'] if m['name']=='Oatmeal | interlaced natural linen')
    rows=[]
    for name in ['GamingNavy_1','GamingPillow_0_0','GamingPillow_1_0']:
        m=next(m for m in g['materials'] if m['name']==name)
        for key,original,current in [('normal',linen['normalTexture'],m['normalTexture']),('roughness',linen['pbrMetallicRoughness']['metallicRoughnessTexture'],m['pbrMetallicRoughness']['metallicRoughnessTexture'])]:
            assert image_hash(s,sb,original)==image_hash(g,b,current),name+' '+key
        assert m['normalTexture']['scale']==linen['normalTexture']['scale']
        sheen=m['extensions']['KHR_materials_sheen'];assert max(sheen['sheenColorFactor'])<.5
        assert sheen['sheenRoughnessFactor']==.5
        dyed=image_hash(g,b,m['pbrMetallicRoughness']['baseColorTexture'])
        assert dyed!=image_hash(s,sb,linen['pbrMetallicRoughness']['baseColorTexture'])
        rows.append({'material':name,'normal_image_sha256':image_hash(g,b,m['normalTexture']),'roughness_image_sha256':image_hash(g,b,m['pbrMetallicRoughness']['metallicRoughnessTexture']),'dyed_albedo_sha256':dyed,'sheen':sheen})
    assert len(g['meshes'])==33 and len(g['nodes'])==33
    assert all(n['name'].replace('_','').isalnum() for n in g['nodes'])
    return {'source_sha256':sh,'candidate_sha256':ch,'original_normal_and_roughness_bytes_exact':True,'legal_ascii_nodes':True,'mesh_count':33,'materials':rows,'native_or_contact_acceptance':False}
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('candidate');p.add_argument('output');a=p.parse_args()
    result=prove(a.source,a.candidate);Path(a.output).write_text(json.dumps(result,indent=2));print(result['candidate_sha256'])
