"""Original editable footrest inspired by the viewed Humanscale FR300 reference.
Not official CAD. Run only in the leased server Blender; no UE/world mutations.
"""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

DESK_SHA='99bdf3fd42eea5fc4cb2fadd52c8cae18c4459a94000b85f7df4c515234ba43d'


def rounded_outline(width,depth,radius,segments=12):
    """Rounded rectangle/capsule without analytically coincident end vertices."""
    if width<=0 or depth<=0 or not 0<radius<=min(width,depth)/2:raise ValueError('Valid physical rounded dimensions required')
    points=[]
    for cx,cy,start in[(width/2-radius,depth/2-radius,0),(-width/2+radius,depth/2-radius,90),(-width/2+radius,-depth/2+radius,180),(width/2-radius,-depth/2+radius,270)]:
        for i in range(segments+1):
            angle=math.radians(start+90*i/segments);point=(cx+radius*math.cos(angle),cy+radius*math.sin(angle))
            if not points or math.dist(point,points[-1])>1e-12:points.append(point)
    if math.dist(points[0],points[-1])<=1e-12:points.pop()
    return points


def build(desk,output,center_x=200.,center_y=-260.,floor=2.5,height=120.):
    import bpy
    import numpy as np
    from mathutils import Vector
    from home_asset_audit import read_gltf
    from structural_rail_source_patch import accessor,world_matrices,transformed
    desk,output=Path(desk),Path(output)
    if hashlib.sha256(desk.read_bytes()).hexdigest()!=DESK_SHA:raise ValueError('Verified genuine LINEA PBR source required')
    if not 95<=height<=152:raise ValueError('Reference dimension height range95..152mm required')
    output.mkdir(parents=True,exist_ok=False)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(desk))
    def unique(label):
        found=[m for m in bpy.data.materials if m.name==label]
        if len(found)!=1:raise ValueError('Exact source PBR material unavailable '+label)
        return found[0]
    wood=unique('Satin walnut | longitudinal grain');endgrain=unique('Satin walnut | end grain')
    metal=unique('Charcoal fine-textured powdercoat');hardware=unique('Blackened steel mounting hardware')
    for obj in list(bpy.data.objects):bpy.data.objects.remove(obj,do_unlink=True)
    # Derive actual provider top-surface UV density, not arbitrary texture tiling.
    doc,blob=read_gltf(desk);matrices=world_matrices(doc);samples=[]
    for p in doc['meshes'][doc['nodes'][44]['mesh']]['primitives']:
        if p['material']!=4:continue
        ps=[transformed(matrices[44],v)for v in accessor(doc,blob,p['attributes']['POSITION'])]
        uv=accessor(doc,blob,p['attributes']['TEXCOORD_0']);top=max(v[1]for v in ps)
        ids=[v[0]for v in accessor(doc,blob,p['indices'])]
        # Boundary positions also occur in separate bevel/edge UV charts.
        # Only vertices referenced by actual horizontal top faces define grain scale.
        top_vertices=set()
        for i in range(0,len(ids),3):
            face=ids[i:i+3]
            if all(abs(ps[j][1]-top)<1e-7 for j in face):
                cross=(Vector(ps[face[1]])-Vector(ps[face[0]])).cross(Vector(ps[face[2]])-Vector(ps[face[0]]))
                if cross.length_squared>0:top_vertices.update(face)
        samples.extend((ps[j],uv[j])for j in sorted(top_vertices))
    a=np.asarray([[p[0],p[2],1.]for p,t in samples]);b=np.asarray([t for p,t in samples])
    coeff=np.linalg.lstsq(a,b,rcond=None)[0];uv_error=float(np.max(np.abs(a@coeff-b)))
    if len(samples)<3 or uv_error>1e-5:raise ValueError('Authored wood top UV mapping is not uniquely affine')
    rubber=bpy.data.materials.new('Original footrest | moulded matte rubber');rubber.use_nodes=True
    bs=rubber.node_tree.nodes.get('Principled BSDF');bs.inputs['Base Color'].default_value=(.012,.014,.014,1);bs.inputs['Roughness'].default_value=.76
    origin=Vector((center_x/100,-center_y/100,floor/100));h=height/1000;objects=[]
    def finish(obj,name,material):
        obj.name='SUB01_ReferenceFootrest_'+name;obj.location+=origin
        if material:obj.data.materials.append(material)
        objects.append(obj);return obj
    def prism(name,outline,z0,z1,material,bevel=0):
        n=len(outline);verts=[(x,y,z)for z in(z0,z1)for x,y in outline]
        faces=[tuple(reversed(range(n))),tuple(range(n,2*n))]+[(i,(i+1)%n,(i+1)%n+n,i+n)for i in range(n)]
        mesh=bpy.data.meshes.new(name);mesh.from_pydata(verts,[],faces);mesh.update();obj=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(obj)
        if bevel:
            mod=obj.modifiers.new('Machined edge radius','BEVEL');mod.width=bevel;mod.segments=4
            bpy.context.view_layer.objects.active=obj;obj.select_set(True);bpy.ops.object.modifier_apply(modifier=mod.name);obj.select_set(False)
        return finish(obj,name,material)
    rounded=rounded_outline
    board=prism('SolidWalnutPlatform',rounded(.374,.284,.013),h-.018,h,wood,.002)
    board.data.materials.append(endgrain);uv=board.data.uv_layers.new(name='ProviderScaleWoodUV')
    for poly in board.data.polygons:
        poly.material_index=0 if abs(poly.normal.z)>.7 else 1
        for li in poly.loop_indices:
            co=board.data.vertices[board.data.loops[li].vertex_index].co
            mapping=np.asarray([co.x,-co.y,1.])@coeff if abs(poly.normal.z)>.7 else np.asarray([co.x,co.z,1.])@coeff
            uv.data[li].uv=tuple(mapping)
    for i,y in enumerate((-.078,0.,.078)):
        o=prism('RubberGripStrip_'+str(i+1),[(x,yy+y)for x,yy in rounded(.320,.028,.014)],h,h+.002,rubber,.0005)
    def cylinder(name,position,radius,depth,material,segments=64):
        bpy.ops.mesh.primitive_cylinder_add(vertices=segments,radius=radius,depth=depth,location=position,rotation=(0,math.pi/2,0))
        o=bpy.context.object
        for p in o.data.polygons:p.use_smooth=len(p.vertices)==4
        return finish(o,name,material)
    def cutter_x(name,x,outline):
        n=len(outline);verts=[(xx,y,z)for xx in(x-.012,x+.012)for y,z in outline]
        faces=[tuple(reversed(range(n))),tuple(range(n,2*n))]+[(i,(i+1)%n,(i+1)%n+n,i+n)for i in range(n)]
        mesh=bpy.data.meshes.new(name);mesh.from_pydata(verts,[],faces);mesh.update();o=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(o);o.location=origin;return o
    for side in(-1,1):
        x=side*.190
        # Real pierced side plate: shaped section, through carry hole and adjustment slot.
        outline=[(-.151,.011),(.151,.011),(.144,h+.012),(.100,h+.018),(-.135,h-.045)]
        n=len(outline);verts=[(xx,y,z)for xx in(x-.002,x+.002)for y,z in outline]
        faces=[tuple(reversed(range(n))),tuple(range(n,2*n))]+[(i,(i+1)%n,(i+1)%n+n,i+n)for i in range(n)]
        me=bpy.data.meshes.new('PiercedSidePlate');me.from_pydata(verts,[],faces);me.update();plate=bpy.data.objects.new('SidePlate',me);bpy.context.collection.objects.link(plate);finish(plate,'PiercedSidePlate_'+str(side),metal)
        holes=[[(.100+.025*math.cos(t),h-.008+.009*math.sin(t))for t in [i*math.tau/64 for i in range(64)]],
               [(yy,zz+h-.027)for yy,zz in rounded(.012,.052,.006)]]
        for index,hole in enumerate(holes):
            cutter=cutter_x('ThroughOpening',x,hole);mod=plate.modifiers.new('Actual through opening '+str(index),'BOOLEAN');mod.operation='DIFFERENCE';mod.solver='EXACT';mod.object=cutter
            bpy.context.view_layer.objects.active=plate;bpy.ops.object.modifier_apply(modifier=mod.name);bpy.data.objects.remove(cutter,do_unlink=True)
        bevel=plate.modifiers.new('Rounded deburred steel edges','BEVEL');bevel.width=.001;bevel.segments=3
        bpy.context.view_layer.objects.active=plate;bpy.ops.object.modifier_apply(modifier=bevel.name)
        # Prove actual holes, including the whole 12mm rocker-axle cross section.
        probes=[(.100,h-.008)]+[(.00599*math.cos(i*math.tau/64),h-.009+.00599*math.sin(i*math.tau/64))for i in range(64)]
        for y,z in probes:
            hit,*_=plate.ray_cast(Vector((x-.020,y,z)),Vector((1,0,0)),distance=.040)
            if hit:raise ValueError('Actual pierced plate blocks carry opening or rocker axle')
        cylinder('AdjustmentKnob_'+str(side),(side*.198,0,h-.009),.018,.010,metal)
        cylinder('KnobSteelHub_'+str(side),(side*.193,0,h-.009),.008,.005,hardware)
        for y in(-.110,.110):cylinder('RollerBearing_'+str(side)+'_'+str(y),(side*.181,y,.016),.011,.012,hardware)
    cylinder('PlatformRockerAxle',(0,0,h-.009),.006,.386,hardware)
    for y in(-.110,.110):
        cylinder('FloorRoller_'+str(y),(0,y,.015),.015,.350,rubber)
        cylinder('FloorRollerAxle_'+str(y),(0,y,.015),.004,.386,hardware)
    # Export only the original designed assembly. All textures stay packed from the genuine source.
    bpy.ops.object.select_all(action='DESELECT')
    for o in objects:o.select_set(True)
    bpy.context.view_layer.update();bpy.ops.file.pack_all()
    blend=output/'reference-footrest.blend';bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    export=output/'reference-footrest.glb';bpy.ops.export_scene.gltf(filepath=str(export),export_format='GLB',use_selection=True,export_apply=True)
    gd,gb=read_gltf(export);gm=world_matrices(gd);points=[];triangles=0;support=[];solid_triangles=[];solid_nodes=[]
    for ni,n in enumerate(gd['nodes']):
        if 'mesh'not in n:continue
        for p in gd['meshes'][n['mesh']]['primitives']:
            ps=[transformed(gm[ni],v)for v in accessor(gd,gb,p['attributes']['POSITION'])];points.extend(ps)
            ids=[i[0]for i in accessor(gd,gb,p['indices'])];triangles+=len(ids)//3
            for k in range(0,len(ids),3):
                t=[ps[j]for j in ids[k:k+3]]
                solid_triangles.append([[v[0]*100,v[2]*100,v[1]*100]for v in t]);solid_nodes.append(ni)
                if max(v[1]for v in t)-min(v[1]for v in t)<1e-7 and abs(t[0][1]-(floor/100+h+.002))<1e-7:
                    support.append([[v[0]*100,v[2]*100,v[1]*100]for v in t])
    lo=[min(p[a]for p in points)for a in range(3)];hi=[max(p[a]for p in points)for a in range(3)]
    if abs(lo[1]-floor/100)>1e-6 or not support:raise ValueError('Actual exported rollers/floor or physical grip support differs')
    from closed_footrest_contact import ClosedFootrest
    closed=ClosedFootrest(solid_triangles,solid_nodes)
    report={'closed_component_topology':closed.proof,'schema':'sub01.original-reference-footrest.v1','reference':'Humanscale FR300 inspiration only; original editable model, not official CAD',
            'source_wood_glb_sha256':DESK_SHA,'wood_uv_affine_max_error':uv_error,'wood_uv_affine_coefficients':coeff.tolist(),
            'center_ue_cm':[center_x,center_y],'actual_floor_ue_cm':floor,'wood_top_ue_cm':floor+h*100,'rubber_support_top_ue_cm':floor+(h+.002)*100,
            'width_reference_m':.406,'depth_reference_m':.302,'actual_bounds_gltf_m':[lo,hi],'actual_dimensions_m':[b-a for a,b in zip(lo,hi)],
            'parts':len(objects),'triangles':triangles,'support_top_world_triangles_ue_cm':support,
            'side_plate_actual_carry_and_axle_ray_probes_clear':True,'original_features':['bevelled rounded solid wood platform','three rounded matte rubber grips','two pierced metal side plates with actual carry holes and adjustment slots','two adjustment knobs','rocker axle','two floor rollers with axle bearings'],
            'glb_sha256':hashlib.sha256(export.read_bytes()).hexdigest(),'blend_sha256':hashlib.sha256(blend.read_bytes()).hexdigest(),
            'native_imported':False,'runtime_ready':False,'upright_pose_solved':False,'house_clearance_proven':False}
    (output/'footrest-source-proof.json').write_text(json.dumps(report,indent=2)+'\n')
    # Small server CPU preview, transparent background; no extra exported geometry.
    bpy.ops.object.camera_add(location=origin+Vector((.55,-.65,.45)))
    camera=bpy.context.object;camera.rotation_euler=(origin+Vector((0,0,h*.5))-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.type='ORTHO';camera.data.ortho_scale=.59
    scene=bpy.context.scene;scene.camera=camera;scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=16
    scene.render.resolution_x=640;scene.render.resolution_y=480;scene.render.resolution_percentage=100;scene.render.film_transparent=True
    scene.world=bpy.data.worlds.new('Neutral source preview world');scene.world.use_nodes=True
    scene.world.node_tree.nodes['Background'].inputs['Color'].default_value=(.5,.5,.5,1);scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value=.3
    for point,power,size in [((.3,-.4,.7),80.,.5),((-.4,.1,.4),45.,.4)]:
        bpy.ops.object.light_add(type='AREA',location=origin+Vector(point));light=bpy.context.object;light.data.energy=power;light.data.shape='DISK';light.data.size=size;light.rotation_euler=(origin+Vector((0,0,h*.5))-light.location).to_track_quat('-Z','Y').to_euler()
    scene.render.filepath=str(output/'footrest-source-preview.png');bpy.ops.render.render(write_still=True)
    print('ACTUAL_FOOTREST_EXPORTED',len(objects),triangles,flush=True)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--desk',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--center-x',type=float,default=200.);parser.add_argument('--center-y',type=float,default=-260.);parser.add_argument('--floor',type=float,default=2.5);parser.add_argument('--height',type=float,default=120.)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);build(args.desk,args.output,args.center_x,args.center_y,args.floor,args.height)
