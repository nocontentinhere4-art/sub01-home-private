"""Hash-bound CC0 kitchen assembly. Audit is light; --blender-export is Runpod-only.

No primitive fillers, no UE actions, no runtime-ready claim. Wood is explicitly
fitted by affine transforms; identifiable authored hardware retains rigid size.
"""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    'base': ('face-frame-base-cabinet.glb', '424076e0bb92c82439d45d34ebf43638b0f89de6e01aecf677bb8700b46f8e80', 18),
    'door': ('shaker-door.glb', '8fd7333614e496afd635b7d7586b1775d6bfaed26b52238b448c3ddc92d86b67', 5),
    'wall': ('wall-cabinet.glb', 'c2f425271bcf3bd8e36110b6aabbe9b9418ca1171d66259a81bf18a5c8731db1', 10),
}
HOME_SHA = '9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b'
SOURCE_REL = 'web/house/assets/real-kitchen-source'
PBR_REL = 'web/house/assets/home_oak_veneer'
PBR_SHA = {'diff.jpg': 'c14681f72f59f17bff568cae7a837641443b607b899f0c279cd64a5638f877a7',
           'rough.jpg': 'ca2af5649b628ef05f196793d68cdca874c12ceb6e9ae566976546d9dd5a2604',
           'normal.jpg': '1297acf7b4476d5ccd83cc8b27be96aa6110f7a9c3a40be0bd767bf81b17db01'}
LOWER_CENTERS = [-3.3, -2.6, -1.9, -1.2]
LOWER_BAYS = [(-3.707, -2.959), (-2.941, -2.259), (-2.241, -1.559), (-1.541, -.693)]
UPPER_CENTERS = [-3.3625, -2.5875, -1.8125, -1.0375]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(root):
    # Actual decoded positions plus every authored node transform, not mislabeled metadata.
    from home_asset_audit import read_gltf
    from structural_rail_source_patch import accessor, world_matrices, transformed
    rows = {}
    for key, (filename, digest, count) in SOURCES.items():
        path = root / SOURCE_REL / filename
        if sha(path) != digest:
            raise ValueError('Reviewed source hash differs: ' + key)
        doc, binary = read_gltf(path)
        matrices = world_matrices(doc)
        parts = []
        for index, node in enumerate(doc['nodes']):
            if 'mesh' not in node:
                continue
            points, triangles = [], 0
            for primitive in doc['meshes'][node['mesh']]['primitives']:
                if primitive.get('mode', 4) != 4:
                    raise ValueError('Nontriangle source geometry')
                points += [transformed(matrices[index], p) for p in accessor(doc, binary, primitive['attributes']['POSITION'])]
                triangles += doc['accessors'][primitive['indices']]['count'] // 3
            bounds = [[f(p[k] for p in points) * .001 for k in range(3)] for f in (min, max)]
            parts.append({'node_index': index, 'name': node['name'], 'bounds_m': bounds,
                          'triangles': triangles, 'vertices': len(points)})
        if len(parts) != count or {p['name'] for p in parts} != {'mesh-' + str(i) for i in range(count)}:
            raise ValueError('Authored part identity differs: ' + key)
        bounds = [[f(p['bounds_m'][side][k] for p in parts) for k in range(3)] for side, f in enumerate((min, max))]
        rows[key] = {'file': filename, 'sha256': digest, 'raw_units': 'millimeters',
                     'unit_scale': .001, 'bounds_m': bounds, 'parts': parts,
                     'dimensions_m': [b-a for a,b in zip(*bounds)]}
    for filename, digest in PBR_SHA.items():
        if sha(root / PBR_REL / filename) != digest:
            raise ValueError('Reviewed scanned PBR differs: ' + filename)
    return rows


def home_contacts(home):
    """Measure source floor/slab faces, not assumed nominal browser coordinates."""
    from home_asset_audit import read_gltf
    from structural_rail_source_patch import accessor, world_matrices, transformed
    if sha(home) != HOME_SHA:
        raise ValueError('Actual full-home source hash differs')
    doc,binary=read_gltf(home);matrices=world_matrices(doc)
    triangles=[];sink_triangles=[];sink_sources=set()
    for node_index,node in enumerate(doc['nodes']):
        if 'mesh' not in node:continue
        for pi,primitive in enumerate(doc['meshes'][node['mesh']]['primitives']):
            if primitive.get('mode',4)!=4:continue
            meta=doc['accessors'][primitive['attributes']['POSITION']]
            if 'min' not in meta or 'max' not in meta:raise ValueError('Source bounds required')
            corners=[transformed(matrices[node_index],(x,y,z)) for x in (meta['min'][0],meta['max'][0]) for y in (meta['min'][1],meta['max'][1]) for z in (meta['min'][2],meta['max'][2])]
            low=[min(v[k] for v in corners) for k in range(3)];high=[max(v[k] for v in corners) for k in range(3)]
            if high[0]<-3.75 or low[0]>-.65 or high[2]<-3.9 or low[2]>-3.15 or low[1]>1.0:continue
            vertices=[transformed(matrices[node_index],v) for v in accessor(doc,binary,primitive['attributes']['POSITION'])]
            indices=[i[0] for i in accessor(doc,binary,primitive['indices'])]
            for j in range(0,len(indices),3):
                tri=[vertices[i] for i in indices[j:j+3]]
                ys=[v[1] for v in tri]
                if max(ys)-min(ys)<1e-5 and (0<=ys[0]<.2 or .8<ys[0]<1.0):
                    triangles.append((node_index,pi,j//3,tri))
                if node_index==164:
                    # Exact source sink assembly, not any geometry within a guessed hole.
                    sink_triangles.append(tri);sink_sources.add((node_index,pi))
    def sample(x,z,lower,upper):
        matches=[]
        for node,prim,index,tri in triangles:
            a,b,c=tri
            det=(b[2]-c[2])*(a[0]-c[0])+(c[0]-b[0])*(a[2]-c[2])
            if abs(det)<1e-12:continue
            u=((b[2]-c[2])*(x-c[0])+(c[0]-b[0])*(z-c[2]))/det
            v=((c[2]-a[2])*(x-c[0])+(a[0]-c[0])*(z-c[2]))/det
            y=a[1]
            if min(u,v,1-u-v)>=-1e-6 and lower<=y<=upper:
                matches.append({'node':node,'primitive':prim,'triangle':index,'y_m':y})
        if not matches:raise ValueError('Actual horizontal source contact missing')
        if upper<.2:
            selected=max(m['y_m'] for m in matches)
            upper_faces=[]
        else:
            # Match both real slab faces separated by the source's55mm thickness;
            # never misread a lower rear support rail as countertop underside.
            pairs=[(a,b) for a in matches for b in matches if abs((b['y_m']-a['y_m'])-.055)<1e-5]
            heights={round(a['y_m'],5) for a,b in pairs}
            if len(heights)!=1:raise ValueError('Unique measured55mm countertop face pair required')
            selected=pairs[0][0]['y_m'];upper_faces=[b for a,b in pairs]
        return {'sample_browser_xz':[x,z],'height_m':selected,'faces':[m for m in matches if abs(m['y_m']-selected)<1e-5], 'paired_slab_top_faces':upper_faces}
    floors=[sample((a+b)/2,-3.55,0,.2) for a,b in LOWER_BAYS]
    slabs=[sample(x,-3.80,.8,1.0) for x in LOWER_CENTERS]
    if max(r['height_m'] for r in floors)-min(r['height_m'] for r in floors)>1e-4:raise ValueError('Kitchen floor is not one measured plane')
    if max(r['height_m'] for r in slabs)-min(r['height_m'] for r in slabs)>1e-4:raise ValueError('Counter underside is not one measured plane')
    sink_points=[]
    underside=slabs[0]['height_m']
    for tri in sink_triangles:
        polygon=list(tri);clipped=[]
        for a,b in zip(polygon,polygon[1:]+polygon[:1]):
            ai=a[1]<=underside;bi=b[1]<=underside
            if ai:clipped.append(a)
            if ai!=bi:
                t=(underside-a[1])/(b[1]-a[1])
                clipped.append(tuple(a[k]+t*(b[k]-a[k]) for k in range(3)))
        sink_points+=clipped
    if not sink_points:raise ValueError('Exact node164 sink geometry below measured slab unavailable')
    all_sink=[v for tri in sink_triangles for v in tri]
    whole=[[f(v[k] for v in all_sink) for k in range(3)] for f in (min,max)]
    expected=[[-3.0525,.745,-3.73],[-2.3475,.936,-3.24]]
    if max(abs(a-b) for side,truth in zip(whole,expected) for a,b in zip(side,truth))>.0001:
        raise ValueError('Exact original sink164 bounds differ')
    sink_bounds=[[f(v[k] for v in sink_points) for k in range(3)] for f in (min,max)]
    return {'source_sha256':HOME_SHA,'floor_samples':floors,'counter_underside_samples':slabs,
            'floor_m':floors[0]['height_m'],'counter_underside_m':slabs[0]['height_m'],
            'sink_conservative_bounds_m':sink_bounds,'sink_source_primitives':[list(v) for v in sorted(sink_sources)],
            'sink_envelope_policy':'Exact SHA-bound node164 triangles clipped below measured slab underside; conservative bounded service cutout volume, not a fabricated bowl.'}


LOWER_FIT_PROFILE = 'actual-carcass-authored-2mm-reveals-v1'


def lower_door_fit(rows, contacts, index):
    """Fit the genuine Shaker wood to its actual carcass, not legacy 650mm leafs.

    The authored600mm base/596mm door and720mm wood/716mm door give2mm
    reveals. Existing unequal real bays remain; hardware stays rigid. Corrected
    lower hinge axes follow each fitted left leaf edge. Upper axes are unchanged.
    """
    if type(index)is not int or not 0<=index<4:raise ValueError('Exact lower cabinet index required')
    source=rows['base'];door=rows['door'];frame=next(p for p in door['parts'] if p['name']=='mesh-1')
    width=source['bounds_m'][1][0]-source['bounds_m'][0][0]
    wood=[p for p in source['parts'] if p['name'] not in {'mesh-14','mesh-15','mesh-16','mesh-17'}]
    height=max(p['bounds_m'][1][1] for p in wood)-min(p['bounds_m'][0][1] for p in wood)
    fw=frame['bounds_m'][1][0]-frame['bounds_m'][0][0];fh=frame['bounds_m'][1][1]-frame['bounds_m'][0][1]
    if max(abs(width-.600),abs(height-.720),abs(fw-.596),abs(fh-.716))>2e-5:raise ValueError('Exact authored600/596 and720/716mm source compatibility required')
    floor=contacts['floor_m'];top=contacts['counter_underside_m'];left,right=LOWER_BAYS[index];bottom=floor+.1
    if not all(math.isfinite(v)for v in (floor,top,left,right))or top-bottom<=.004 or right-left<=.004:raise ValueError('Measured positive carcass bounds required')
    reveal=.002;center=[(left+right)/2,(bottom+top)/2,-3.215]
    return {'profile':LOWER_FIT_PROFILE,'index':index,'carcass_bounds_xy_m':[[left,bottom],[right,top]],'reveal_m':reveal,
            'center_browser_m':center,'dimensions_m':[right-left-2*reveal,top-bottom-2*reveal,.051],
            'hinge_browser_m':[left+reveal,center[1],-3.192],
            'expected_panel_bounds_browser_m':[[left+reveal,bottom+reveal,-3.225],[right-reveal,top-reveal,-3.205]],
            'legacy_hinge_delta_browser_m':[left+reveal-(LOWER_CENTERS[index]-.325),center[1]-.44,0.]}


def verify_lower_closed_fit(bpy, report):
    """Measure exported authored frame vertices before accepting source export."""
    if report.get('lower_door_fit_profile')!=LOWER_FIT_PROFILE:raise ValueError('Current measured lower-door fit profile required')
    bpy.context.view_layer.update();measured=[]
    for index in range(4):
        fit=lower_door_fit(report['source'],report['actual_home_contacts'],index)
        obj=bpy.data.objects.get('Lower_cabinet_hinge_'+str(index+1)+'__mesh-1')
        if obj is None:raise ValueError('Actual authored Shaker frame missing')
        points=[obj.matrix_world @ v.co for v in obj.data.vertices]
        browser=[(p.x,p.z,-p.y)for p in points]
        bounds=[[fn(p[k]for p in browser)for k in range(3)]for fn in (min,max)]
        error=max(abs(a-b)for actual,expected in zip(bounds,fit['expected_panel_bounds_browser_m'])for a,b in zip(actual,expected))
        if error>1e-5:raise ValueError('Actual lower closed-frame/reveal fit differs')
        measured.append({**fit,'actual_panel_bounds_browser_m':bounds,'actual_vertex_bounds_error_m':error})
    return {'profile':LOWER_FIT_PROFILE,'passed':True,'source_serialization_bounds_limit_m':1e-5,'doors':measured,'collision_epsilon_unchanged_m':0.}


def plan(rows, contacts=None):
    assemblies = []
    floor=contacts["floor_m"] if contacts else None
    underside=contacts["counter_underside_m"] if contacts else None
    if contacts is None:
        raise ValueError("Measured actual kitchen floor/counter/sink source required")
    def add(name, source, center, dimensions, rigid=(), hinge=None):
        lo, hi = rows[source]['bounds_m']
        source_center = [(a+b)/2 for a,b in zip(lo,hi)]
        scale = [dimensions[k]/(hi[k]-lo[k]) for k in range(3)]
        if source == 'door':
            source_center[2]=0.0  # authored wood panel center, NOT pull-inclusive51mm bounding center
        if source == 'base':
            # Authored100mm feet stay rigid: wood begins at100mm and reaches existing slab.
            wood_low=min(p['bounds_m'][0][1] for p in rows[source]['parts'] if p['name'] not in rigid)
            wood_high=max(p['bounds_m'][1][1] for p in rows[source]['parts'] if p['name'] not in rigid)
            source_center[1]=(wood_low+wood_high)/2
            scale[1]=(underside-floor-.1)/(wood_high-wood_low)
            center[1]=(underside+floor+.1)/2
        assemblies.append({'name': name, 'source': source, 'center_browser_m': center,
                           'target_dimensions_m': dimensions, 'source_center_m': source_center,
                           'affine_scale_after_mm_normalization': scale,
                           'rigid_parts': list(rigid), 'hinge_browser_m': hinge})
    for i, (x, bay) in enumerate(zip(LOWER_CENTERS, LOWER_BAYS), 1):
        add('Lower_cabinet_body_'+str(i), 'base', [(bay[0]+bay[1])/2,(underside+floor)/2,-3.55],
            [bay[1]-bay[0],underside-floor,.62], ('mesh-14','mesh-15','mesh-16','mesh-17'))
        # Panel +/-10mm and authored pull geometry are retained; not the 51mm total stretched as wood.
        fit=lower_door_fit(rows,contacts,i-1)
        add('Lower_cabinet_hinge_'+str(i), 'door', fit['center_browser_m'],fit['dimensions_m'],
            ('mesh-2','mesh-3','mesh-4'),fit['hinge_browser_m'])
    upper_door_back=-3.545+rows['door']['bounds_m'][0][2]
    upper_body_rear=-3.89
    upper_body_front=upper_door_back-.002
    for i, x in enumerate(UPPER_CENTERS, 1):
        # Keep the authored hinge fixed; stop the carcass behind the real wood panel.
        add('Upper_cabinet_body_'+str(i), 'wall', [x,2.05,(upper_body_rear+upper_body_front)/2],
            [.775,.7,upper_body_front-upper_body_rear])
        # Original authored pivot -1.548 + worldX -2.2, actual attachUpper hingeOffset +.014.
        add('Cabinet hinge '+str(i), 'door', [x,2.05,-3.545], [.771,.66,.051],
            ('mesh-2','mesh-3','mesh-4'), [x-.771/2,2.05,-3.531])
    return {'schema': 'sub01.real-kitchen-derived-plan.v1', 'lower_door_fit_profile':LOWER_FIT_PROFILE, 'source': rows,
            'assemblies': assemblies, 'actual_home_contacts':contacts, 'hardware_policy': 'rigid .001 scale about each authored part center; center follows panel fit',
            'wood_policy': 'explicit nonuniform affine fit; source files untouched; no manufacturer unscaled-size claim',
            'pbr': {'source': 'https://polyhaven.com/a/oak_veneer_01', 'license': 'CC0',
                    'scan_coverage_m': 1.83, 'files_sha256': PBR_SHA},
            'preserve_existing': ['real sink', 'countertop', 'under-cabinet light', 'eight hinge names and functions', 'four upper hinge positions'],
            'native_ready': False, 'contact_verified': False, 'hinge_collision_verified': False,
            'feasibility_gaps': ['Only source-identified upper top/side/back/frame boards may receive bounded actual sink164 service cutouts; lower supports/legs retained, all resulting native clearances require proof.',
                                 'Rigid source legs must contact actual floor while fitted wood reaches slab underside; export refuses known mismatch.',
                                 'Measured eight door closed bounds/swept collision and all native hinge bindings require actual Editor proof.',
                                 'Existing countertop and four unequal lower bays are retained; no fabricated filler meshes.']}


def export_blender(root, output, report):
    if not str(root.resolve()).startswith('/workspace/'):
        raise RuntimeError('Heavy Blender export allowed only on authorized Runpod workspace')
    import bpy
    from mathutils import Vector
    bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
    templates = {}
    for key, row in report['source'].items():
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=str(root / SOURCE_REL / row['file']))
        imported = list(set(bpy.data.objects)-before)
        templates[key] = []
        for obj in imported:
            if obj.type != 'MESH':
                continue
            # glTF→Blender axes x,-z,y; freeze each authored world transform before duplication.
            data = obj.data.copy()
            for vertex in data.vertices:
                world = obj.matrix_world @ vertex.co
                vertex.co = Vector((world.x*.001,world.z*.001,-world.y*.001))
            templates[key].append((obj.name, data))
        if {n for n,_ in templates[key]} != {p['name'] for p in row['parts']}:
            raise ValueError('Blender importer changed source part names')
        for obj in imported:
            bpy.data.objects.remove(obj, do_unlink=True)
    oak = bpy.data.materials.new('SUB01_RealKitchen_CC0_Oak'); oak.use_nodes = True
    nodes, links = oak.node_tree.nodes, oak.node_tree.links
    shader = next(n for n in nodes if n.type == 'BSDF_PRINCIPLED')
    for filename, socket in [('diff.jpg','Base Color'),('rough.jpg','Roughness'),('normal.jpg','Normal')]:
        image=bpy.data.images.load(str(root/PBR_REL/filename),check_existing=True)
        image.colorspace_settings.name='sRGB' if filename=='diff.jpg' else 'Non-Color'
        texture=nodes.new('ShaderNodeTexImage');texture.image=image
        if filename=='normal.jpg':
            normal=nodes.new('ShaderNodeNormalMap');links.new(texture.outputs['Color'],normal.inputs['Color']);links.new(normal.outputs['Normal'],shader.inputs[socket])
        else:links.new(texture.outputs['Color'],shader.inputs[socket])
    hardware=bpy.data.materials.new('SUB01_RealKitchen_AuthoredHardware');hardware.use_nodes=True
    bsdf=hardware.node_tree.nodes.get('Principled BSDF');bsdf.inputs['Metallic'].default_value=1;bsdf.inputs['Roughness'].default_value=.3
    exported=[];contacts=[]
    for assembly in report['assemblies']:
        pivot=assembly['hinge_browser_m'] or assembly['center_browser_m']
        parent=bpy.data.objects.new(assembly['name'],None);bpy.context.collection.objects.link(parent)
        parent.location=(pivot[0],-pivot[2],pivot[1])
        for name, template in templates[assembly['source']]:
            data=template.copy(); part=next(p for p in report['source'][assembly['source']]['parts'] if p['name']==name)
            pc=[(a+b)/2 for a,b in zip(*part['bounds_m'])];rigid=name in assembly['rigid_parts']
            fitted_center=[assembly['center_browser_m'][k]+(pc[k]-assembly['source_center_m'][k])*assembly['affine_scale_after_mm_normalization'][k] for k in range(3)]
            if assembly['source']=='base' and rigid:
                fitted_center[1]=pc[1]+.1+report['actual_home_contacts']['floor_m']  # exact rigid100mm foot to unchanged floor
            for vertex in data.vertices:
                p=list(vertex.co)
                target=[fitted_center[k]+(p[k]-pc[k])*(1 if rigid else assembly['affine_scale_after_mm_normalization'][k]) for k in range(3)]
                vertex.co=(target[0]-pivot[0],-(target[2]-pivot[2]),target[1]-pivot[1])
            obj=bpy.data.objects.new(assembly['name']+'__'+name,data);bpy.context.collection.objects.link(obj);obj.parent=parent
            if not rigid:
                data.materials.clear();data.materials.append(oak)
            elif not data.materials:
                data.materials.append(hardware)
            data.update()
            uv=data.uv_layers.new(name='Metric_CC0_1p83m')
            for poly in data.polygons:
                axes=sorted(range(3),key=lambda k:abs(poly.normal[k]))[:2]
                for loop_index in poly.loop_indices:
                    v=data.vertices[data.loops[loop_index].vertex_index].co
                    uv.data[loop_index].uv=(v[axes[0]]/1.83,v[axes[1]]/1.83)
            exported.append({'assembly':assembly['name'],'source_part':name,'vertices':len(data.vertices),'polygons':len(data.polygons),'rigid':rigid})
            if assembly['source']=='base' and rigid:
                low=min(v.co.z+parent.location.z for v in data.vertices)
                contacts.append({'assembly':assembly['name'],'part':name,'foot_bottom_m':low,'floor_contact_error_m':abs(low-report['actual_home_contacts']['floor_m'])})
    report['exported_parts']=exported;report['leg_contacts']=contacts
    report['lower_closed_fit_proof']=verify_lower_closed_fit(bpy,report)
    measured_sink_cutouts(bpy,report)
    collision_checks=verify_source_collisions(bpy,report)
    report['source_collision_checks']=collision_checks
    # Do not silently warp rigid legs to make the derived geometry appear buildable.
    report['source_export_ready']=all(c['floor_contact_error_m']<=.0001 for c in contacts) and collision_checks['passed']
    output.mkdir(parents=True,exist_ok=True)
    if not report['source_export_ready']:
        (output/'real-kitchen-refused.json').write_text(json.dumps(report,indent=2))
        raise RuntimeError('Measured floor/sink/door clearance checks refused derived kitchen; inspect real-kitchen-refused.json')
    bpy.ops.export_scene.gltf(filepath=str(output/'real-kitchen.glb'),export_format='GLB',export_yup=True)
    report['derived_sha256']=sha(output/'real-kitchen.glb')
    (output/'real-kitchen.json').write_text(json.dumps(report,indent=2))


def source_bvh(bpy, objects):
    from mathutils.bvhtree import BVHTree
    vertices=[];polygons=[];owners=[]
    for obj in objects:
        offset=len(vertices)
        vertices.extend(obj.matrix_world @ v.co for v in obj.data.vertices)
        polygons.extend([offset+i for i in poly.vertices] for poly in obj.data.polygons)
        owners.extend([obj.name]*len(obj.data.polygons))
    return BVHTree.FromPolygons(vertices,polygons,all_triangles=False,epsilon=0.0),owners


def bounds_bvh(bounds):
    from mathutils.bvhtree import BVHTree
    lo,hi=bounds
    browser=[(x,y,z) for x in (lo[0],hi[0]) for y in (lo[1],hi[1]) for z in (lo[2],hi[2])]
    vertices=[(x,-z,y) for x,y,z in browser]
    faces=[(0,1,3,2),(4,6,7,5),(0,4,5,1),(2,3,7,6),(0,2,6,4),(1,5,7,3)]
    return BVHTree.FromPolygons(vertices,faces,epsilon=0.0)


def measured_sink_cutouts(bpy,report):
    """Subtract only exact authored top boards with the measured retained sink envelope."""
    part=next(p for p in report['source']['base']['parts'] if p['name']=='mesh-7')
    lo,hi=part['bounds_m']
    if part['triangles']!=12 or abs(lo[1]-.70200177)>.00001 or abs(hi[1]-.71999823)>.00001:
        raise ValueError('Exact authored removable top-board identity differs')
    # Exact affected upper wood boards may be cut; lower supports and ALL rigid feet stay unchanged.
    allowed={'mesh-0','mesh-3','mesh-7','mesh-8','mesh-13'}
    sink=report['actual_home_contacts']['sink_conservative_bounds_m']
    pad=.003
    cutter_bounds=[[sink[0][0]-pad,sink[0][1]-pad,sink[0][2]-pad],
                   [sink[1][0]+pad,report['actual_home_contacts']['counter_underside_m']+.01,sink[1][2]+pad]]
    center=[(a+b)/2 for a,b in zip(*cutter_bounds)];dims=[b-a for a,b in zip(*cutter_bounds)]
    bpy.ops.mesh.primitive_cube_add(size=1,location=(center[0],-center[2],center[1]))
    cutter=bpy.context.object;cutter.name='TEMP_MeasuredSinkSubtractionTool'
    cutter.dimensions=(dims[0],dims[2],dims[1]);bpy.context.view_layer.update()
    changes=[]
    try:
        for obj in list(bpy.data.objects):
            if obj.type!='MESH' or not obj.name.startswith('Lower_cabinet_body_'):continue
            part_name=obj.name.rsplit('__',1)[-1]
            if part_name not in allowed:continue
            tree,_=source_bvh(bpy,[obj])
            if not tree.overlap(bounds_bvh(cutter_bounds)):continue
            before=len(obj.data.polygons)
            old_bottom=min((obj.matrix_world @ v.co).z for v in obj.data.vertices)
            bpy.context.view_layer.objects.active=obj
            modifier=obj.modifiers.new('ActualSinkMeasuredCutout','BOOLEAN');modifier.operation='DIFFERENCE';modifier.solver='EXACT';modifier.object=cutter
            # Authored CAD triangulation has per-face seams and T-junctions.
            # Exact hole-tolerant evaluation changes no input positions; final BVH remains strict.
            modifier.use_hole_tolerant=True;modifier.use_self=True
            bpy.ops.object.modifier_apply(modifier=modifier.name)
            if len(obj.data.polygons)<1:raise ValueError('Sink cutout unexpectedly removed entire authored top board')
            new_bottom=min((obj.matrix_world @ v.co).z for v in obj.data.vertices)
            if abs(old_bottom-new_bottom)>1e-6:raise ValueError('Service cutout removed a lower board support')
            changes.append({'object':obj.name,'authored_part':part_name,'before_polygons':before,
                            'after_polygons':len(obj.data.polygons),'operation':'measured sink envelope subtraction',
                            'cutter_bounds_browser_m':cutter_bounds,'clearance_m':pad})
    finally:
        bpy.data.objects.remove(cutter,do_unlink=True)
    if not changes:raise ValueError('Measured sink did not identify any authored cabinet top-board intersection')
    report['measured_sink_boolean']=changes


def verify_source_collisions(bpy,report):
    """Strict actual derived triangle BVHs, no collision-ignore or count-only readiness."""
    bpy.context.view_layer.update()
    bodies=[o for o in bpy.data.objects if o.type=='MESH' and ('_cabinet_body_' in o.name)]
    static,owners=source_bvh(bpy,bodies)
    sink=report['actual_home_contacts']['sink_conservative_bounds_m']
    pairs=static.overlap(bounds_bvh(sink))
    sink_hits=sorted({owners[p[0]] for p in pairs})
    # AABB containment catches a wholly embedded board even without intersecting envelope faces.
    for obj in bodies:
        for vertex in obj.data.vertices:
            w=obj.matrix_world @ vertex.co;point=(w.x,w.z,-w.y)
            if all(sink[0][k]<point[k]<sink[1][k] for k in range(3)):
                sink_hits.append(obj.name);break
    sink_hit_evidence=[]
    body_polygons=[(obj,poly) for obj in bodies for poly in obj.data.polygons]
    for index,_ in pairs[:12]:
        obj,poly=body_polygons[index]
        points=[obj.matrix_world @ obj.data.vertices[i].co for i in poly.vertices]
        browser=[(v.x,v.z,-v.y) for v in points]
        sink_hit_evidence.append({'object':obj.name,'polygon_index':poly.index,
            'vertices_browser_m':[list(v) for v in browser]})
    door_rows=[]
    parents=[o for o in bpy.data.objects if o.type=='EMPTY' and ('hinge_' in o.name or o.name.startswith('Cabinet hinge '))]
    if len(parents)!=8:raise ValueError('All eight fixed hinge parents required for sweep test')
    for parent in parents:
        children=[o for o in parent.children if o.type=='MESH']
        tested=0;failure=None
        try:
            for step in range(90):
                angle=-math.pi*.49*step/89
                parent.rotation_euler.z=angle;bpy.context.view_layer.update()
                tree,_=source_bvh(bpy,children);hits=tree.overlap(static);tested+=1
                if hits:
                    failure={'angle_rad':angle,'actual_carcass_objects':sorted({owners[b] for a,b in hits})[:16],
                             'triangle_intersections':len(hits)}
                    break
        finally:
            parent.rotation_euler.z=0;bpy.context.view_layer.update()
        door_rows.append({'hinge':parent.name,'tested_poses':tested,'closed_and_sweep_passed':failure is None,'failure':failure})
    return {'epsilon_m':0.0,'sink_source_bvh_clear':not sink_hits,'sink_intersections':sorted(set(sink_hits)),
            'sink_intersection_evidence':sink_hit_evidence,
            'doors':door_rows,'passed':not sink_hits and all(r['closed_and_sweep_passed'] for r in door_rows),
            'native_ready':False,'scope':'Derived source triangles only; not native simple-collision or physical capsule proof'}


def main():
    args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--home',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--blender-export',action='store_true')
    a=parser.parse_args(args);report=plan(inventory(a.root),home_contacts(a.home))
    if a.blender_export:
        try:
            export_blender(a.root,a.output,report)
        except BaseException as error:
            report['source_export_ready']=False
            report['error_type']=type(error).__name__
            report['error']=str(error)[:1000]
            a.output.mkdir(parents=True,exist_ok=True)
            (a.output/'real-kitchen-refused.json').write_text(json.dumps(report,indent=2))
            raise
    else:
        a.output.mkdir(parents=True,exist_ok=True)
        (a.output/'real-kitchen-plan.json').write_text(json.dumps(report,indent=2))
        print(json.dumps({'parts':{k:len(v['parts']) for k,v in report['source'].items()},'assemblies':len(report['assemblies']),'native_ready':False}))

if __name__=='__main__':main()
