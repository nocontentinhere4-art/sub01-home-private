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


def plan(rows):
    assemblies = []
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
            scale[1]=(.8675-.1)/(wood_high-wood_low)
            center[1]=(.8675+.1)/2
        assemblies.append({'name': name, 'source': source, 'center_browser_m': center,
                           'target_dimensions_m': dimensions, 'source_center_m': source_center,
                           'affine_scale_after_mm_normalization': scale,
                           'rigid_parts': list(rigid), 'hinge_browser_m': hinge})
    for i, (x, bay) in enumerate(zip(LOWER_CENTERS, LOWER_BAYS), 1):
        add('Lower_cabinet_body_'+str(i), 'base', [(bay[0]+bay[1])/2,.8675/2,-3.55],
            [bay[1]-bay[0],.8675,.62], ('mesh-14','mesh-15','mesh-16','mesh-17'))
        # Panel +/-10mm and authored pull geometry are retained; not the 51mm total stretched as wood.
        add('Lower_cabinet_hinge_'+str(i), 'door', [x,.44,-3.215], [.65,.76,.051],
            ('mesh-2','mesh-3','mesh-4'), [x-.325,.44,-3.192])
    for i, x in enumerate(UPPER_CENTERS, 1):
        add('Upper_cabinet_body_'+str(i), 'wall', [x,2.05,-3.71], [.775,.7,.36])
        # Original authored pivot -1.548 + worldX -2.2, actual attachUpper hingeOffset +.014.
        add('Cabinet hinge '+str(i), 'door', [x,2.05,-3.545], [.771,.66,.051],
            ('mesh-2','mesh-3','mesh-4'), [x-.771/2,2.05,-3.531])
    return {'schema': 'sub01.real-kitchen-derived-plan.v1', 'source': rows,
            'assemblies': assemblies, 'hardware_policy': 'rigid .001 scale about each authored part center; center follows panel fit',
            'wood_policy': 'explicit nonuniform affine fit; source files untouched; no manufacturer unscaled-size claim',
            'pbr': {'source': 'https://polyhaven.com/a/oak_veneer_01', 'license': 'CC0',
                    'scan_coverage_m': 1.83, 'files_sha256': PBR_SHA},
            'preserve_existing': ['real sink', 'countertop', 'under-cabinet light', 'four lower hinge positions', 'four upper hinge positions'],
            'native_ready': False, 'contact_verified': False, 'hinge_collision_verified': False,
            'feasibility_gaps': ['Source base has a solid top board beneath the sink: actual sink bowl/top-board intersection must be measured before import.',
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
                fitted_center[1]=pc[1]+.1  # exact rigid100mm foot to unchanged floor
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
                contacts.append({'assembly':assembly['name'],'part':name,'foot_bottom_m':low,'floor_contact_error_m':abs(low)})
    report['exported_parts']=exported;report['leg_contacts']=contacts
    # Do not silently warp rigid legs to make the derived geometry appear buildable.
    report['source_export_ready']=all(c['floor_contact_error_m']<=.001 for c in contacts)
    output.mkdir(parents=True,exist_ok=True)
    if not report['source_export_ready']:
        (output/'real-kitchen-refused.json').write_text(json.dumps(report,indent=2))
        raise RuntimeError('Rigid authored legs do not meet fitted floor; reviewed attachment correction required')
    bpy.ops.export_scene.gltf(filepath=str(output/'real-kitchen.glb'),export_format='GLB',export_yup=True)
    report['derived_sha256']=sha(output/'real-kitchen.glb')
    (output/'real-kitchen.json').write_text(json.dumps(report,indent=2))


def main():
    args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--blender-export',action='store_true')
    a=parser.parse_args(args);report=plan(inventory(a.root))
    if a.blender_export:export_blender(a.root,a.output,report)
    else:
        a.output.mkdir(parents=True,exist_ok=True)
        (a.output/'real-kitchen-plan.json').write_text(json.dumps(report,indent=2))
        print(json.dumps({'parts':{k:len(v['parts']) for k,v in report['source'].items()},'assemblies':len(report['assemblies']),'native_ready':False}))

if __name__=='__main__':main()
