"""Constant root-frame conversion only; preserve physical world poses at new body origin."""
import copy,json,math,struct,hashlib
from pathlib import Path
from home_asset_audit import read_gltf
from structural_rail_source_patch import accessor,world_matrices

OLD_BODY=(200.025,-199.8,-.6)
NEW_BODY=(200.025,-232.3,4.65)
ROOT_LOCAL_DELTA=(0.,-5.25,-32.5) # mixamo parent scale.01, x->-X,y->Z,z->-Y


def mapped(doc,binary):
    d=copy.deepcopy(doc);out=bytearray(binary);anim=d['animations'][0];matches=[]
    for channel in anim['channels']:
        if channel['target']['path']=='translation'and d['nodes'][channel['target']['node']].get('name')=='mixamorig:Hips':matches.append(channel)
    if len(matches)!=1:raise ValueError('Unique actual Hips translation required')
    sampler=anim['samplers'][matches[0]['sampler']];a=d['accessors'][sampler['output']];rows=accessor(doc,binary,sampler['output']);assert a['type']=='VEC3'and a['componentType']==5126
    while len(out)%4:out.append(0)
    start=len(out)
    for row in rows:out.extend(struct.pack('<fff',*[x+delta for x,delta in zip(row,ROOT_LOCAL_DELTA)]))
    d['bufferViews'].append({'buffer':0,'byteOffset':start,'byteLength':len(out)-start});newa={'bufferView':len(d['bufferViews'])-1,'componentType':5126,'count':len(rows),'type':'VEC3'};d['accessors'].append(newa);sampler['output']=len(d['accessors'])-1;d['buffers'][0]['byteLength']=len(out)
    assert d['nodes']==doc['nodes']
    return d,bytes(out)


def key_worlds(doc,binary,key):
    d=copy.deepcopy(doc)
    for channel in d['animations'][0]['channels']:
        sampler=d['animations'][0]['samplers'][channel['sampler']];rows=accessor(d,binary,sampler['output']);d['nodes'][channel['target']['node']][channel['target']['path']]=rows[key]
    W=world_matrices(d);return {n['name']:W[i]for i,n in enumerate(d['nodes'])if n.get('name','').startswith('mixamorig:')}


def run():
    root=Path('docs/proposed/upright-footrest-source');reports=[]
    for name in ['SUB01_SeatedIdle_upright_footrest.glb','SUB01_SitDown_upright_footrest.glb','SUB01_GetUp_upright_footrest_ShortStart.glb']:
        p=root/name;d,b=read_gltf(p);new,nb=mapped(d,b);F=d['accessors'][d['animations'][0]['samplers'][0]['input']]['count'];maximum=0.;rotation=0.
        for f in range(F):
            oldW=key_worlds(d,b,f);newW=key_worlds(new,nb,f);assert len(oldW)==len(newW)==65
            for joint in oldW:
                a,c=oldW[joint],newW[joint]
                pa=[OLD_BODY[0]-a[0][3]*100,OLD_BODY[1]-a[2][3]*100,OLD_BODY[2]+a[1][3]*100];pc=[NEW_BODY[0]-c[0][3]*100,NEW_BODY[1]-c[2][3]*100,NEW_BODY[2]+c[1][3]*100]
                maximum=max(maximum,math.dist(pa,pc));rotation=max(rotation,max(abs(a[r][col]-c[r][col])for r in range(3)for col in range(3)))
        assert maximum<.02 and rotation==0
        reports.append({'source':str(p),'source_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'all_frames':F,'all_joints':65,'maximum_physical_world_translation_error_cm':maximum,'world_linear_matrix_difference':rotation,'nodes_unchanged':new['nodes']==d['nodes'],'original_binary_prefix_unchanged':nb[:len(b)]==b})
    report={'schema':'sub01.upright-source-frame-neutral-identity.v1','old_source_body_origin_ue_cm':OLD_BODY,'new_source_body_origin_ue_cm':NEW_BODY,'hips_local_delta_cm':ROOT_LOCAL_DELTA,'clips':reports,'skin_implication':'Identical linear bone transforms plus uniformly bounded world translation error bound every normalized-weight LBS point by the same translation error; no vertex weights/IBMs/shape changed. Full vertex skin simulation not performed.','no_new_clip_written':True,'no_native_activation':True,'anchor_clearance_pass':False}
    (root/'source-frame-neutral-identity.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':run()
