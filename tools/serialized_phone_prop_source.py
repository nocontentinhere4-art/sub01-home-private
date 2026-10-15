"""Exact old five-part phone source under an explicitly UNVERIFIED wrist-frame hypothesis."""
import hashlib,json,struct,math
from pathlib import Path


def add_phone(bpy,np,Matrix,Quaternion,Vector,BVHTree,owner_world,owner_names,owner_objects,output):
    source=Path('/workspace/sub01-private-recovered-project/Sub01HomeLab/SourceAssets/full-home.glb')
    raw=source.read_bytes();p=12;doc=binary=None
    while p<len(raw):
        size,kind=struct.unpack_from('<II',raw,p);data=raw[p+8:p+8+size]
        if kind==0x4e4f534a:doc=json.loads(data)
        elif kind==0x004e4942:binary=data
        p+=size+8
    assert doc and binary
    def access(i):
        a=doc['accessors'][i];v=doc['bufferViews'][a['bufferView']];assert not a.get('sparse')and not v.get('extensions')
        dt=np.dtype({5121:'u1',5122:'<i2',5123:'<u2',5125:'<u4',5126:'<f4'}[a['componentType']]);w={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT4':16}[a['type']]
        x=np.ndarray((a['count'],w),dtype=dt,buffer=binary,offset=v.get('byteOffset',0)+a.get('byteOffset',0),strides=(v.get('byteStride',dt.itemsize*w),dt.itemsize)).astype(float)
        if a.get('normalized'):x/=np.iinfo(dt).max
        return x
    parents={c:i for i,n in enumerate(doc['nodes'])for c in n.get('children',[])};worlds={}
    def world(i):
        if i not in worlds:
            n=doc['nodes'][i];q=n.get('rotation',[0,0,0,1]);m=Matrix(np.array(n['matrix']).reshape(4,4).T.tolist())if 'matrix'in n else Matrix.LocRotScale(Vector(n.get('translation',[0,0,0])),Quaternion((q[3],*q[:3])),Vector(n.get('scale',[1,1,1])))
            worlds[i]=world(parents[i])@m if i in parents else m
        return worlds[i]
    wrist=owner_world(owner_names['mixamorig:RightHand']);wq=wrist.to_quaternion();wp=wrist.translation
    # Native FRotator quaternion formula, copied as math, not guessed Euler order.
    angles=(-22.42641,59.35637,4.24461)
    sp,sy,sr=[math.sin(math.radians(v)/2)for v in angles];cp,cy,cr=[math.cos(math.radians(v)/2)for v in angles]
    mountq=Quaternion((cr*cp*cy+sr*sp*sy,cr*sp*sy-sr*cp*cy,-cr*sp*cy-sr*cp*sy,cr*cp*sy-sr*sp*cy))
    uq=Quaternion((wq.w,-wq.x,-wq.z,-wq.y));center=Vector((wp.x,wp.z,wp.y))+uq@Vector((.0075422,-.0968499,.0471232));rotation=uq@mountq
    expected=[((270,-292,85.8),(3.75,7.5,.75)),((270,-298.2,86.7),(.95,.15,.05)),((266.2,-294,85.8),(.1,1.25,.2)),((273.8,-294,85.8),(.1,.7,.2)),((270,-292,86.6),(3.35,6.85,0))]
    hands={}
    for obj in owner_objects:
        if 'cc0adult'in obj.name.lower():
            side='Left'if'left'in obj.name.lower()else'Right';hands[side]=BVHTree.FromPolygons([v.co for v in obj.data.vertices],[tuple(f.vertices)for f in obj.data.polygons],all_triangles=True,epsilon=0)
    assert set(hands)=={'Left','Right'}
    parts=[];original_center=Vector((2.7,-2.92,.858))
    for index in range(132,137):
        n=doc['nodes'][index];assert 'mesh'in n
        for pi,primitive in enumerate(doc['meshes'][n['mesh']]['primitives']):
            attrs=primitive['attributes'];positions=access(attrs['POSITION']);original=[];posed=[]
            for value in positions:
                value=world(index)@Vector(value);ue=Vector((value.x,value.z,value.y));original.append(list(ue*100))
                ue=center+rotation@(ue-original_center);posed.append((ue.x,-ue.y,ue.z))
            mn=np.min(original,axis=0);mx=np.max(original,axis=0);exp_c,exp_e=expected[index-132]
            assert np.max(np.abs((mn+mx)/2-exp_c))<.001 and np.max(np.abs((mx-mn)/2-exp_e))<.001,(index,mn,mx)
            triangles=access(primitive['indices']).astype(int).reshape(-1,3);mesh=bpy.data.meshes.new('ActualOldPhoneSource'+str(index));mesh.from_pydata(posed,[],triangles.tolist());mesh.update();obj=bpy.data.objects.new(mesh.name,mesh);bpy.context.scene.collection.objects.link(obj)
            material_spec=doc['materials'][primitive['material']];pbr=material_spec.get('pbrMetallicRoughness',{});mat=bpy.data.materials.new('ExactPhoneSource_'+str(index));mat.use_nodes=True;nodes=mat.node_tree.nodes;shader=nodes.get('Principled BSDF');shader.inputs['Base Color'].default_value=pbr.get('baseColorFactor',[1,1,1,1]);shader.inputs['Metallic'].default_value=pbr.get('metallicFactor',1);shader.inputs['Roughness'].default_value=pbr.get('roughnessFactor',1)
            if 'baseColorTexture'in pbr:
                assert 'KHR_materials_unlit'in material_spec.get('extensions',{})
                ti=pbr['baseColorTexture']['index'];image=doc['images'][doc['textures'][ti]['source']];view=doc['bufferViews'][image['bufferView']];start=view.get('byteOffset',0);path=output/('actual-old-phone-source-'+str(index)+'.png');path.write_bytes(binary[start:start+view['byteLength']]);pixels=bpy.data.images.load(str(path),check_existing=False);tex=nodes.new('ShaderNodeTexImage');tex.image=pixels;emit=nodes.new('ShaderNodeEmission');mat.node_tree.links.new(tex.outputs['Color'],emit.inputs['Color']);mat.node_tree.links.new(emit.outputs['Emission'],nodes.get('Material Output').inputs['Surface']);uv=access(attrs['TEXCOORD_0']);layer=mesh.uv_layers.new(name='UVMap')
                for face in mesh.polygons:
                    for loop in face.loop_indices:value=uv[mesh.loops[loop].vertex_index];layer.data[loop].uv=(value[0],1-value[1])
            mesh.materials.append(mat);tree=BVHTree.FromPolygons(posed,triangles.tolist(),all_triangles=True,epsilon=0)
            parts.append({'original_node':index,'name':n.get('name'),'triangles':len(triangles),'original_center_cm':((mn+mx)/2).tolist(),'original_extent_cm':((mx-mn)/2).tolist(),'hypothesis_hand_triangle_candidates':{side:len(tree.overlap(hand))for side,hand in hands.items()}})
    return {'source_sha256':hashlib.sha256(raw).hexdigest(),'exact_source_nodes':[132,133,134,135,136],'source_parts':parts,'mount_source':'existing unreal_derived_phone_visual_review.py exact offset/euler, evaluated CONDITIONAL on source wrist frame equalling native FBX wrist frame','native_wrist_basis_verified':False,'old_native_mount_transferred_or_accepted':False,'phone_screen':'exact old source texture, NOT live screen','contact_accepted':False}
