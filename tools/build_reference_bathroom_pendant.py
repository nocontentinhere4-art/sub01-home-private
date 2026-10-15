"""Build a real-size CC0 pendant for the private bathroom, on server Blender.

Uses the cached Poly Haven model, shortening ONLY its thin cable to3cm. Actual
home source triangle42/node158 supplies the canopy plane, checked at ninepoints.
No native/map/activity changes. This is an authored candidate, not acceptance.
"""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

HOME_SHA = '9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b'
ASSET_SHA = 'f88b5d0a81fa813457a77474e7e4e812f97ad5fac2109ba03ddb183274be3f8c'


def canopy_proof(home, radius):
    from home_asset_audit import read_gltf
    from structural_rail_source_patch import world_matrices
    from prepare_real_wc_bundle import node_geometry
    if hashlib.sha256(Path(home).read_bytes()).hexdigest() != HOME_SHA:
        raise ValueError('Exact original955 home required')
    doc, binary = read_gltf(home)
    rows = node_geometry(doc, binary, 158, world_matrices(doc))
    probes = [(-2.6, 1.55)]+[(-2.6+radius*math.cos(k*math.pi/4), 1.55+radius*math.sin(k*math.pi/4)) for k in range(8)]
    result = []
    for x,z in probes:
        hits = []
        for primitive,row in enumerate(rows):
            for ti,f in enumerate(row['faces']):
                a,b,c = [row['points'][i] for i in f]
                v = [b[i]-a[i] for i in range(3)]; w = [c[i]-a[i] for i in range(3)]
                n = [v[1]*w[2]-v[2]*w[1],v[2]*w[0]-v[0]*w[2],v[0]*w[1]-v[1]*w[0]]
                length = math.sqrt(sum(t*t for t in n)); det = v[0]*w[2]-v[2]*w[0]
                if length==0 or n[1]/length>-.98 or abs(det)<1e-12:continue
                u = ((x-a[0])*w[2]-(z-a[2])*w[0])/det
                t = (v[0]*(z-a[2])-v[2]*(x-a[0]))/det
                if min(u,t,1-u-t)<-1e-8:continue
                y = a[1]+u*v[1]+t*w[1]
                if 5.<y<6.5:hits.append({'primitive':primitive,'triangle':ti,'y':y,'normal_y':n[1]/length})
        if len(hits)!=1 or hits[0]['triangle']!=42 or abs(hits[0]['y']-5.949999809265137)>1e-7:
            raise ValueError('Actual canopy must touch unique real roof underside')
        result.append({'probe_xz': [x,z], **hits[0]})
    return result


def build(asset, home, output, separate_materials=False):
    import bpy
    from mathutils import Vector
    from build_real_lamps import primitive_vertices, measure_pendant, cable_remap
    asset=Path(asset); home=Path(home); output=Path(output)
    if hashlib.sha256(asset.read_bytes()).hexdigest()!=ASSET_SHA:
        raise ValueError('Exact cached Poly Haven source required')
    if output.exists():raise ValueError('Candidate output must be new')
    measurements=measure_pendant(primitive_vertices(asset))
    probes=canopy_proof(home, measurements['canopy_radius'])
    ceiling=probes[0]['y']; cable_length=.03
    cx,cz=measurements['canopy_center_xz']
    origin=(-2.6-cx,1.55-cz,ceiling-measurements['canopy_top_y'])
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(asset))
    meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
    if len(meshes)!=1:raise ValueError('Original complete pendant must remain one mesh')
    obj=meshes[0]
    if any(abs(v-1)>1e-8 for v in obj.scale) or obj.parent is not None:
        raise ValueError('Unexpected source scale/parent; no guessed transform')
    counts=(len(obj.data.vertices),len(obj.data.polygons)); original_materials=list(obj.data.materials)
    topology=[tuple(p.vertices) for p in obj.data.polygons]
    uv_before=[[tuple(v.uv) for v in layer.data] for layer in obj.data.uv_layers]
    for v in obj.data.vertices:
        v.co.z=cable_remap(v.co.z,measurements['cable_band_y'],cable_length)
    obj.location=Vector((origin[0],-origin[1],origin[2]))
    obj.name='SUB01_RealBathroomPendant_PolyHaven'
    obj.data.update();bpy.context.view_layer.update()
    points=[obj.matrix_world@v.co for v in obj.data.vertices]
    bounds=[[min(p[a] for p in points) for a in range(3)],[max(p[a] for p in points) for a in range(3)]]
    if abs(bounds[1][2]-ceiling)>1e-6 or bounds[0][2]-3.0525<2.1:
        raise ValueError('Fixture must touch measured roof with real standing headroom')
    if not (-3.76<bounds[0][0] and bounds[1][0]<-2.13 and -2.5<bounds[0][1] and bounds[1][1]<-.7):
        raise ValueError('Fixture outside actual dry-zone wall/shower clearances')
    if (counts!=(len(obj.data.vertices),len(obj.data.polygons)) or original_materials!=list(obj.data.materials)
            or topology!=[tuple(p.vertices) for p in obj.data.polygons]
            or uv_before!=[[tuple(v.uv) for v in layer.data] for layer in obj.data.uv_layers]):
        raise ValueError('Source topology/materials changed')
    bpy.context.view_layer.objects.active=obj
    bpy.ops.object.select_all(action='DESELECT');obj.select_set(True)
    def corners(objects):
        result=[]
        for part in objects:
            part.data.calc_loop_triangles()
            uv=part.data.uv_layers.active
            for triangle in part.data.loop_triangles:
                name=part.data.materials[triangle.material_index].name
                points=tuple(tuple(part.matrix_world@part.data.vertices[i].co) for i in triangle.vertices)
                tex=tuple(tuple(uv.data[i].uv) for i in triangle.loops) if uv else ()
                result.append((name,points,tex))
        return sorted(result)
    before_corners=corners([obj])
    if separate_materials:
        bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.separate(type='MATERIAL');bpy.ops.object.mode_set(mode='OBJECT')
        for part in [o for o in bpy.context.scene.objects if o.type=='MESH']:
            if len(part.data.materials)!=1:raise ValueError('One physical material role per part required')
            material=part.data.materials[0].name
            role={'modern_ceiling_lamp_01_glass':'Glass','modern_ceiling_lamp_01':'Metal','modern_ceiling_globe':'Globe'}.get(material)
            if role is None:raise ValueError('Unexpected genuine material role')
            part.name='SUB01_RealBathroomPendant_'+role
    parts=[o for o in bpy.context.scene.objects if o.type=='MESH']
    if corners(parts)!=before_corners:raise ValueError('Material split changed world triangle corners or UVs')
    bpy.ops.object.select_all(action='DESELECT')
    for part in parts:part.select_set(True)
    output.mkdir(parents=True)
    bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(output/'bathroom-pendant.blend'))
    target=output/'bathroom-pendant.glb'
    bpy.ops.export_scene.gltf(filepath=str(target),export_format='GLB',use_selection=True,export_animations=False,export_yup=True)
    bulb=measurements['bulb_center']
    bulb_world=[origin[0]+bulb[0],origin[2]+cable_remap(bulb[1],measurements['cable_band_y'],cable_length),origin[1]+bulb[2]]
    report={'schema':'sub01.real-bathroom-pendant-source.v1','source_url':'https://polyhaven.com/a/modern_ceiling_lamp_01',
            'license':'CC0','source_gltf_sha256':ASSET_SHA,'home_sha256':HOME_SHA,'source_measurements':measurements,
            'actual_roof_source_probes':probes,'new_cable_length_m':cable_length,'uniform_scale':1.,
            'native_material_parts':len(parts),'split_world_triangle_corners_and_uvs_exact':True,'original_vertices':counts[0],'original_polygons':counts[1],'source_topology_materials_retained':True,
            'world_bounds_blender_m':bounds,'standing_headroom_m':bounds[0][2]-3.0525,
            'bulb_ue_cm':[bulb_world[0]*100,bulb_world[2]*100,bulb_world[1]*100],
            'glb_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
            'blend_sha256':hashlib.sha256((output/'bathroom-pendant.blend').read_bytes()).hexdigest(),
            'native_imported':False,'native_light_installed':False,'source_collision_complete':False,'runtime_ready':False,
            'pending':['Full source/native fixture collision check','Native independent switched light and actual first-person ON/OFF review']}
    (output/'bathroom-pendant.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--asset',required=True);p.add_argument('--home',required=True);p.add_argument('--output',required=True);p.add_argument('--separate-materials',action='store_true')
    args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
    a=p.parse_args(args);build(a.asset,a.home,a.output,a.separate_materials)
