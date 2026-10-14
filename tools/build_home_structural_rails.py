"""Server-only replacement stair/landing rails with real tread/floor/wall anchors.

blender -b --python tools/build_home_structural_rails.py -- --source SOURCE.glb
  --source-sha SHA --output-dir PRIVATE_DIR
Pure --audit-source works without Blender. Never replaces tread, wall or route
geometry. Batched rail meshes are surgically patched: nonrail source triangles,
normals and UV are preserved in a scoped remainder before originals are hidden.
Coordinates are actual home.js metres, Y up; Blender is (x,-z,y).
"""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from home_asset_audit import read_gltf, node_matrix, matmul, IDENTITY

SOURCE_SHA='9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b'


def old_rails():
    rows=[]
    def add(name,a,b,r):rows.append(dict(name=name,a=a,b=b,radius=r))
    for x in (-.25,.85):
        add('incline', [x,.9,2.55],[x,3.9,-1.7],.03)
        for i in range(9):
            z=2.55-i*.5;h=3*(2.55-z)/4.25
            add('incline post',[x,h,z],[x,h+.9,z],.013)
    z=-1.6
    while z<4:
        add('west loft post',[-.12,3,z],[-.12,3.95,z],.014);z+=.34
    add('west loft rail',[-.12,3.98,-1.7],[-.12,3.98,4],.033)
    z=-3.8
    while z<-1.7:
        add('north landing post',[.85,3,z],[.85,3.98,z],.014);z+=.35
    add('north landing rail',[.85,3.98,-3.9],[.85,3.98,-1.7],.033)
    return rows


def source_audit(source, expected_sha=SOURCE_SHA):
    path=Path(source)
    actual=hashlib.sha256(path.read_bytes()).hexdigest()
    if actual!=expected_sha or expected_sha!=SOURCE_SHA:raise ValueError('Actual source GLB identity differs')
    doc,binary=read_gltf(path)
    parents={c:i for i,n in enumerate(doc['nodes']) for c in n.get('children',[])}
    cache={}
    def world(i):
        if i not in cache:cache[i]=matmul(world(parents[i]) if i in parents else IDENTITY,node_matrix(doc['nodes'][i]))
        return cache[i]
    candidates=[]
    for i,node in enumerate(doc['nodes']):
        if 'mesh' not in node:continue
        primitives=doc['meshes'][node['mesh']]['primitives']
        if len(primitives)!=1:continue
        primitive=primitives[0];position=doc['accessors'][primitive['attributes']['POSITION']]
        if 'min' not in position or 'max' not in position:continue
        lo,hi=position['min'],position['max'];matrix=world(i)
        def transform(p):return [sum(matrix[r][c]*v for c,v in enumerate((*p,1))) for r in range(3)]
        # Original beam is a centered CylinderGeometry whose local long axis is Y.
        if abs(lo[1]+hi[1])>.001 or max(abs(lo[0]),abs(hi[0]),abs(lo[2]),abs(hi[2]))>.04:continue
        radius=max(abs(lo[0]),abs(hi[0]),abs(lo[2]),abs(hi[2]))
        candidates.append(dict(source_node_index=i,source_name=node.get('name'),a=transform((0,lo[1],0)),b=transform((0,hi[1],0)),radius=radius,material_index=primitive.get('material')))
    matched=[];errors=[];used=set()
    def distance(a,b):return math.sqrt(sum((x-y)**2 for x,y in zip(a,b)))
    for expected in old_rails():
        found=[r for r in candidates if abs(r['radius']-expected['radius'])<.0002 and min(max(distance(r['a'],expected['a']),distance(r['b'],expected['b'])),max(distance(r['b'],expected['a']),distance(r['a'],expected['b'])))<.001]
        if len(found)!=1 or found[0]['source_node_index'] in used:
            errors.append({'expected_beam':expected,'matches':len(found)})
            continue
        row=found[0];used.add(row['source_node_index'])
        matched.append(dict(row,expected_role=expected['name'],actor_object_name='full-home_node_'+str(row['source_node_index']),component_name='StaticMeshComponent0'))
    batched=False
    if errors:
        from structural_rail_source_patch import select
        matched,errors=select(doc,binary,old_rails());batched=True
        if not errors and {row['source_node_index'] for row in matched}!={162,163}:
            errors.append({'reason':'Actual reviewed affected source nodes must be exactly162 oak and163 metal; no other geometry may be replaced'})
    return {'source_sha256':actual,'source':str(path),'old_rail_count':len(old_rails()),'matched_rails':matched,'errors':errors,'batched_source_patch':batched},doc,binary


def replacement_parts():
    parts=[]
    def beam(name,a,b,r,material='metal'):
        parts.append(dict(name=name,shape='beam',a=a,b=b,radius=r,material=material))
    def plate(name,c,size,material='metal'):
        parts.append(dict(name=name,shape='box',centre=c,size=size,material=material))
    for side,x in (('West',-.13),('East',.76)):
        first=(x,3/17+.0235+.9,2.425);last=(x,3+.0235+.9,-1.575)
        beam(side+' inclined oak grip',first,last,.028,'oak')
        for i in range(0,17,2):
            z=2.55-(i+.5)*.25;surface=(i+1)*3/17+.0235;top=surface+.9
            plate(side+f' tread anchor plate {i}',(x,surface+.003,z),(.065,.006,.075))
            beam(side+f' tread anchored post {i}',(x,surface+.006,z),(x,top-.029,z),.012)
            beam(side+f' post foot collar {i}',(x,surface+.006,z),(x,surface+.038,z),.021)
            # A real fixing saddle under the timber grip; not a hanging endpoint.
            angle=math.atan(3/4.25)
            plate(side+f' grip saddle {i}',(x,top-math.cos(angle)*.0325,z-math.sin(angle)*.0325),(.035,.009,.035))
            parts[-1]['pitch_blender_x']=angle
            for dx in (-.021,.021):
                beam(side+f' countersunk anchor {i} {dx}',(x+dx,surface+.006,z),(x+dx,surface+.009,z),.0035)
        # Tread-to-landing grip transition is visibly offset above the slab.
        landing_x=-.26 if side=='West' else .76
        beam(side+' landing offset connector',last,(landing_x,3.98,-1.80),.028,'oak')
    # West loft guard is supported ON the real loft floor, not over empty shaft.
    beam('West supported loft grip',(-.26,3.98,-1.80),(-.26,3.98,3.88),.028,'oak')
    for i in range(18):
        z=-1.80+i*(5.68/17);surface=3.025
        plate(f'West loft baseplate {i}',(-.26,surface+.003,z),(.07,.006,.075))
        beam(f'West loft supported baluster {i}',(-.26,surface+.006,z),(-.26,3.948,z),.012)
        plate(f'West loft timber saddle {i}',(-.26,3.948,z),(.035,.009,.035))
    beam('East supported north landing grip',(.76,3.98,-3.80),(.76,3.98,-1.80),.028,'oak')
    for i in range(7):
        z=-3.80+i*(2/6);surface=3.025
        plate(f'East landing baseplate {i}',(.76,surface+.003,z),(.065,.006,.075))
        beam(f'East landing post {i}',(.76,surface+.006,z),(.76,3.948,z),.012)
        plate(f'East landing saddle {i}',(.76,3.948,z),(.035,.009,.035))
    # Rear wall inner face z=-3.91 (actual .18m wall centred z=-4).
    # Returned ends and three standoff brackets visibly meet that wall face.
    beam('North wall mounted oak grip',(-.13,3.98,-3.80),(.76,3.98,-3.80),.028,'oak')
    for x in (-.13,.315,.76):
        beam(f'North wall mounting rosette {x}',(x,3.90,-3.91),(x,3.90,-3.898),.034)
        beam(f'North wall bracket standoff {x}',(x,3.90,-3.898),(x,3.90,-3.80),.009)
        beam(f'North wall bracket upstand {x}',(x,3.90,-3.80),(x,3.948,-3.80),.009)
        plate(f'North wall grip fixing saddle {x}',(x,3.948,-3.80),(.035,.009,.035))
    beam('North west wall return',(-.13,3.98,-3.80),(-.13,3.98,-3.91),.028,'oak')
    # Plain end rosette makes the return a real wall connection.
    beam('North west return wall flange',(-.13,3.98,-3.91),(-.13,3.98,-3.90),.038)
    return parts


def oak_grip_paths():
    """Join exact touching grip segments into continuous uncapped bend paths."""
    remaining=[p for p in replacement_parts() if p['material']=='oak']
    paths=[]
    while remaining:
        part=remaining.pop(0);points=[part['a'],part['b']]
        while True:
            matches=[(i,p['b'] if p['a']==points[-1] else p['a']) for i,p in enumerate(remaining) if p['a']==points[-1] or p['b']==points[-1]]
            if len(matches)>1:raise ValueError('Ambiguous structural grip branching')
            if not matches:break
            index,endpoint=matches[0];remaining.pop(index);points.append(endpoint)
        paths.append(points)
    return paths


def part_bounds(part):
    if part['shape']=='beam':
        return [[min(a,b)-part['radius'] for a,b in zip(part['a'],part['b'])],[max(a,b)+part['radius'] for a,b in zip(part['a'],part['b'])]]
    size=list(part['size'])
    if 'pitch_blender_x' in part:
        angle=part['pitch_blender_x'];size[1],size[2]=abs(math.cos(angle))*size[1]+abs(math.sin(angle))*size[2],abs(math.cos(angle))*size[2]+abs(math.sin(angle))*size[1]
    return [[c-s/2 for c,s in zip(part['centre'],size)],[c+s/2 for c,s in zip(part['centre'],size)]]


def geometry_checks():
    errors=[]
    for part in replacement_parts():
        lo,hi=part_bounds(part)
        # Conservatively reject loft soffit intersections; allowed top-floor
        # baseplates sit above y3.025. No fixture relies on hiding an intersection.
        if lo[0]<-.2 and lo[1]<3 and hi[1]>2.88 and lo[2]<4 and hi[2]>-4:
            errors.append(part['name']+' intersects west loft soffit')
        if 'tread anchor plate' in part['name'] and not (lo[0]>=-.21 and hi[0]<=.81):
            errors.append(part['name']+' unsupported outside actual tread')
        if 'loft baseplate' in part['name'] and hi[0]>-.2:
            errors.append(part['name']+' unsupported over stair shaft')
    return errors


def build(source,out,expected_sha=SOURCE_SHA,remove_reviewed_desk_stem=False):
    import bpy
    from mathutils import Vector,Matrix
    audit,doc,binary=source_audit(source,expected_sha)
    if audit['errors']:raise ValueError('Exact isolated original rail proof failed: '+json.dumps(audit['errors']))
    if geometry_checks():raise ValueError(geometry_checks())
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    # Reuse the actual source rail material pixels and PBR factors, not a new tint.
    def source_material(role,index=None):
        if index is None:
            record=next(row for row in audit['matched_rails'] if row['expected_role']==('incline' if role=='oak' else 'incline post'));index=record['material_index']
        data=doc['materials'][index];pbr=data.get('pbrMetallicRoughness',{})
        material=bpy.data.materials.new('SUB01_StructuralRail_'+role);material.use_nodes=True
        bsdf=material.node_tree.nodes.get('Principled BSDF')
        bsdf.inputs['Base Color'].default_value=pbr.get('baseColorFactor',[1,1,1,1])
        bsdf.inputs['Roughness'].default_value=pbr.get('roughnessFactor',1)
        bsdf.inputs['Metallic'].default_value=pbr.get('metallicFactor',1)
        def texture(info,label,colour=True):
            if not info:return None
            tex=doc['textures'][info['index']];im=doc['images'][tex['source']]
            if 'bufferView' not in im:raise ValueError('Actual source rail image must be embedded')
            view=doc['bufferViews'][im['bufferView']];start=view.get('byteOffset',0)
            path=out/(role+'-'+label+('.png' if im.get('mimeType')=='image/png' else '.jpg'))
            path.write_bytes(binary[start:start+view['byteLength']])
            image=bpy.data.images.load(str(path));image.colorspace_settings.name='sRGB' if colour else 'Non-Color'
            node=material.node_tree.nodes.new('ShaderNodeTexImage');node.image=image
            return node
        colour=texture(pbr.get('baseColorTexture'),'source-colour')
        if colour:
            # Source rail tint factor is applied explicitly, not discarded.
            multiply=material.node_tree.nodes.new('ShaderNodeMixRGB');multiply.blend_type='MULTIPLY';multiply.inputs[0].default_value=1;multiply.inputs[2].default_value=pbr.get('baseColorFactor',[1,1,1,1])
            material.node_tree.links.new(colour.outputs['Color'],multiply.inputs[1]);material.node_tree.links.new(multiply.outputs[0],bsdf.inputs['Base Color'])
        normal=texture(data.get('normalTexture'),'source-normal',False)
        if normal:
            mapping=material.node_tree.nodes.new('ShaderNodeNormalMap');mapping.inputs['Strength'].default_value=data['normalTexture'].get('scale',1)
            material.node_tree.links.new(normal.outputs['Color'],mapping.inputs['Color']);material.node_tree.links.new(mapping.outputs['Normal'],bsdf.inputs['Normal'])
        return material
    materials={role:source_material(role) for role in ('oak','metal')}
    def point(p):return Vector((p[0],-p[2],p[1]))
    preserved=[];additional_removals=[]
    if remove_reviewed_desk_stem:
        from desk_lamp_stem_source_patch import select_stem,union_remainder_selection
        stem=select_stem(doc,binary,audit['source_sha256'])
        if stem['triangle_indices']!=list(range(1800,1840)) or stem['selected_triangle_count']!=40:raise ValueError('Reviewed exact legacy stem triangle identity differs')
        union_remainder_selection(audit['matched_rails'],stem) # Refuse overlaps/count drift.
        additional_removals.append(stem)
    if audit['batched_source_patch']:
        from structural_rail_source_patch import accessor,transformed,world_matrices
        matrices=world_matrices(doc)
        removed={}
        for row in [*audit['matched_rails'],*additional_removals]:
            key=(row['source_node_index'],row['primitive_index']);removed.setdefault(key,set()).update(row['triangle_indices'])
        affected=sorted({key[0] for key in removed})
        for node_index in affected:
            node=doc['nodes'][node_index]
            for primitive_index,primitive in enumerate(doc['meshes'][node['mesh']]['primitives']):
                raw_positions=accessor(doc,binary,primitive['attributes']['POSITION'])
                indices=[v[0] for v in accessor(doc,binary,primitive['indices'])] if 'indices' in primitive else list(range(len(raw_positions)))
                excluded=removed.get((node_index,primitive_index),set())
                faces=[indices[j*3:j*3+3] for j in range(len(indices)//3) if j not in excluded]
                if not faces:continue
                used=sorted({i for face in faces for i in face});mapping={i:j for j,i in enumerate(used)}
                positions=[point(transformed(matrices[node_index],raw_positions[i])) for i in used]
                mesh=bpy.data.meshes.new(f'SUB01_PreservedSource_{node_index}_{primitive_index}');mesh.from_pydata(positions,[],[[mapping[i] for i in face] for face in faces]);mesh.update()
                obj=bpy.data.objects.new(mesh.name,mesh);bpy.context.collection.objects.link(obj)
                material_index=primitive.get('material')
                obj.data.materials.append(source_material(f'preserved-{material_index}',material_index))
                if 'TEXCOORD_0' in primitive['attributes']:
                    raw_uv=accessor(doc,binary,primitive['attributes']['TEXCOORD_0']);layer=mesh.uv_layers.new(name='OriginalSourceUV')
                    for loop in mesh.loops:
                        uv=raw_uv[used[loop.vertex_index]];layer.data[loop.index].uv=(uv[0],1-uv[1])
                if 'NORMAL' in primitive['attributes']:
                    raw_normals=accessor(doc,binary,primitive['attributes']['NORMAL']);normal_matrix=Matrix(matrices[node_index]).to_3x3().inverted().transposed()
                    normals=[point(normal_matrix@Vector(raw_normals[used[loop.vertex_index]])).normalized() for loop in mesh.loops]
                    for polygon in mesh.polygons:polygon.use_smooth=True
                    mesh.normals_split_custom_set(normals)
                preserved.append({'source_node_index':node_index,'primitive_index':primitive_index,'material_index':material_index,'original_triangle_count':len(indices)//3,'removed_rail_triangles':len(excluded),'preserved_triangle_count':len(faces),'preserved_vertex_count':len(used),'source_positions_normals_uv_preserved':True})
    for index,points in enumerate(oak_grip_paths()):
        curve=bpy.data.curves.new(f'SUB01_ContinuousOakGrip_{index}','CURVE');curve.dimensions='3D';curve.resolution_u=1;curve.bevel_depth=.028;curve.bevel_resolution=3;curve.use_fill_caps=True
        spline=curve.splines.new('POLY');spline.points.add(len(points)-1)
        for entry,p in zip(spline.points,points):entry.co=(*point(p),1)
        obj=bpy.data.objects.new(curve.name,curve);bpy.context.collection.objects.link(obj);obj.data.materials.append(materials['oak'])
        bpy.context.view_layer.objects.active=obj;obj.select_set(True);bpy.ops.object.convert(target='MESH');obj.select_set(False)
    for part in replacement_parts():
        if part['material']=='oak':continue
        if part['shape']=='beam':
            a,b=point(part['a']),point(part['b']);direction=b-a
            bpy.ops.mesh.primitive_cylinder_add(vertices=24,radius=part['radius'],depth=direction.length,location=(a+b)/2)
            obj=bpy.context.object;obj.rotation_mode='QUATERNION';obj.rotation_quaternion=direction.to_track_quat('Z','Y')
            for polygon in obj.data.polygons:polygon.use_smooth=len(polygon.vertices)==4
        else:
            bpy.ops.mesh.primitive_cube_add(size=1,location=point(part['centre']))
            obj=bpy.context.object;obj.dimensions=(part['size'][0],part['size'][2],part['size'][1])
            bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
            if 'pitch_blender_x' in part:obj.rotation_euler.x=part['pitch_blender_x']
            bevel=obj.modifiers.new('Machined edge','BEVEL');bevel.width=.001;bevel.segments=2
            bpy.context.view_layer.objects.active=obj;bpy.ops.object.modifier_apply(modifier=bevel.name)
        obj.name='SUB01_StructuralRail_'+part['name'];obj.data.materials.append(materials[part['material']])
    bpy.ops.object.select_all(action='SELECT')
    glb=out/'structural-stair-rails.glb'
    bpy.ops.export_scene.gltf(filepath=str(glb),export_format='GLB',use_selection=True,export_yup=True,export_animations=False)
    hidden={row['source_node_index']:{k:row[k] for k in ('source_node_index','source_name','actor_object_name','component_name')} for row in audit['matched_rails']}
    report={'schema':'sub01-private-structural-rails-v1','source_audit':audit,'additional_source_removals':additional_removals,'output_sha256':hashlib.sha256(glb.read_bytes()).hexdigest(),'replacement_only':not preserved,'scoped_original_mesh_remainder':preserved,'parts':replacement_parts(),'geometry_checks':geometry_checks(),
            'placement':'Global source metres preserved; UE glTF import coordinates, no additive scene origin offset',
            'original_hide_manifest':[hidden[i] for i in sorted(hidden)],'unchanged':['all stair/tread/slab/wall geometry','walkable staircase collision','native route graph','light/device/brain state'],
            'native_acceptance_pending':True}
    (out/'structural-stair-rails.json').write_text(json.dumps(report,indent=2)+'\n')
    bpy.ops.wm.save_as_mainfile(filepath=str(out/'structural-stair-rails.blend'))
    print('SUB01_STRUCTURAL_RAIL_BUILD '+json.dumps({'glb':str(glb),'sha256':report['output_sha256'],'old_rail_count':len(audit['matched_rails']),'part_count':len(report['parts']),'geometry_checks':report['geometry_checks']}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source',required=True);parser.add_argument('--source-sha',default=SOURCE_SHA);parser.add_argument('--output-dir',required=True);parser.add_argument('--audit-source',action='store_true');parser.add_argument('--remove-reviewed-desk-stem',action='store_true',help='Opt-in union remainder only when replacement desk lamp is ready; never import two overlapping remainders')
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else None)
    if args.audit_source:
        result,_,_=source_audit(args.source,args.source_sha);print(json.dumps(result,indent=2))
    else:build(args.source,args.output_dir,args.source_sha,args.remove_reviewed_desk_stem)
