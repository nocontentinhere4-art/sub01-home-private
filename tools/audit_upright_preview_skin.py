"""Read-only comparison of original glTF LBS against evaluated Blender owner skin.
Runs only on leased server CPU against the preserved repository-fitted SitDown source preview.
"""
import json
import sys
from pathlib import Path

def run():
    import bpy
    import numpy as np
    sys.path.insert(0,'/workspace/sub01-home-private/upright-footrest-full-9cd/tools')
    import export_seat_fit_source as E
    import fit_seat_pelvis_pitch as P
    import life_gltf as G
    root=Path('/workspace/sub01-home-private/upright-footrest-full-9cd');E.OWNER=Path('/workspace/sub01-private-recovered-project/Sub01HomeLab/SourceAssets/owner-with-clips-unreal.glb');base=E.Source.load(root/'private-audit/seat-fit-source.npz')
    source=G.Gltf(E.OWNER);names=[E.short(source.doc['nodes'][i]['name'])for i in source.doc['skins'][0]['joints']]
    if names!=base.names:raise ValueError('Canonical joint indexing differs source NPZ')
    scene_path='/workspace/sub01-home-private/upright-raw-sit-preview-r1/uid1001/output/upright-source-diagnostic.blend';bpy.ops.wm.open_mainfile(filepath=scene_path);bpy.context.scene.frame_set(20);bpy.context.view_layer.update();deps=bpy.context.evaluated_depsgraph_get()
    body=bpy.data.objects['DiagnosticActualBodyPlacement'];meshes=[o for o in body.children_recursive if o.type=='MESH'];skin=P.owner_skin(stride=1);positions,joints,weights=skin
    from structural_rail_source_patch import world_matrices
    document_world=world_matrices(source.doc);bind_world=np.asarray([document_world[i]for i in source.doc['skins'][0]['joints']]);bind_points=P.skin_points(skin,base.ibm,bind_world[None])[0];bind_delta=bind_world@base.ibm
    clip=G.Gltf(root/'web/room/mh_mx/room_mx_stand_to_sit.glb');W,_=E.joint_worlds(clip,base.names,[20/30]);posed=E.to_ue(P.skin_points(skin,base.ibm,W))[0];posed[:,:2]+=np.asarray([-3.875,32.5])
    def weight_key(js,ws):return tuple(sorted((names[int(j)],round(float(w),5))for j,w in zip(js,ws)if w>1e-7))
    def key(uv,w,material):return (None if uv is None else tuple(round(float(x),5)for x in uv),w,material)
    by={};source_meta=[];seen=set();cursor=0
    for node in source.doc['nodes']:
        if 'mesh'not in node or node.get('skin')!=0 or node['mesh']in seen:continue
        seen.add(node['mesh'])
        for primitive in source.doc['meshes'][node['mesh']]['primitives']:
            attributes=primitive['attributes'];rawweights=E.accessor(source,attributes['WEIGHTS_0']);keep=rawweights.sum(1)>0
            uv=E.accessor(source,attributes['TEXCOORD_0'])if 'TEXCOORD_0'in attributes else [None]*len(rawweights)
            material=source.doc['materials'][primitive['material']]['name']
            for vi in np.flatnonzero(keep):
                i=cursor;cursor+=1;source_meta.append((uv[vi],material));by.setdefault(key(uv[vi],weight_key(joints[i],weights[i]),material),[]).append(i)
    if cursor!=len(positions):raise ValueError('UV source indexing differs exact P.owner_skin stream')
    rows=[];unmatched=[];maximum=0.;compared=0
    invbody=body.matrix_world.inverted()
    for obj in meshes:
        if not obj.vertex_groups:continue
        evaluated=obj.evaluated_get(deps);mesh=evaluated.to_mesh();count=0;errors=[];groups={g.index:E.short(g.name)for g in obj.vertex_groups}
        try:
            vertex_uv={};vertex_material={}
            for polygon in obj.data.polygons:
                material=obj.data.materials[polygon.material_index].name if obj.data.materials[polygon.material_index]else None
                for li in polygon.loop_indices:
                    vi=obj.data.loops[li].vertex_index
                    vertex_material.setdefault(vi,material)
                    if obj.data.uv_layers.active:vertex_uv.setdefault(vi,tuple(obj.data.uv_layers.active.data[li].uv))
            if len(mesh.vertices)!=len(obj.data.vertices):raise ValueError('Unexpected topology-changing preview modifier')
            for vi in range(0,len(obj.data.vertices),97):
                v=obj.data.vertices[vi];bind=invbody@obj.matrix_world@v.co;p=(bind.x,bind.z,-bind.y);ws=[(groups[g.group],float(g.weight))for g in v.groups if g.weight>1e-7];total=sum(w for _,w in ws)
                if not total:continue
                wk=tuple(sorted((n,round(w/total,5))for n,w in ws));uv=vertex_uv.get(vi);material=vertex_material.get(vi);ids=[]
                for candidate_uv in ([uv,(uv[0],1-uv[1])]if uv is not None else[None]):ids.extend(by.get(key(candidate_uv,wk,material),[]))
                ids=list(set(ids))
                if not ids or max((float(np.linalg.norm(positions[i]-positions[ids[0]]))for i in ids),default=0)>1e-7:
                    unmatched.append({'object':obj.name,'vertex':vi,'uv':uv,'material':material,'source_candidates':len(ids)});continue
                actual=obj.matrix_world@mesh.vertices[vi].co;point=np.asarray([actual.x*100,-actual.y*100,actual.z*100]);distance=min(float(np.linalg.norm(point-posed[i]))for i in ids);maximum=max(maximum,distance);errors.append(distance);count+=1;compared+=1
            rows.append({'object':obj.name,'vertices':len(obj.data.vertices),'compared':count,'maximum_error_cm':max(errors,default=None)})
        finally:evaluated.to_mesh_clear()
    report={'schema':'sub01.raw-capture-preview-skin-parity.v1','canonical_owner_joint_indexing_equals_npz':True,'document_bind_times_ibm_first':bind_delta[0].tolist(),'document_bind_times_ibm_max_difference_from_first':float(np.abs(bind_delta-bind_delta[0]).max()),'repository_fitted_clip_untouched':True,'provider_raw_capture_available':False,'source_time_s':20/30,'blender_frame':20,'sample_stride':97,'matching':'unchanged UV + named joint weights + material; ambiguous UV/weight duplicates excluded','compared_vertices':compared,'unmatched_samples':len(unmatched),'unmatched_examples':unmatched[:12],'max_source_lbs_vs_blender_world_error_cm':maximum,'objects':rows,'native_readiness':False}
    out=Path('/workspace/sub01-home-private/upright-raw-sit-preview-r1/uid1001/output/raw-gltf-vs-blender-skin.json');out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
if __name__=='__main__':run()
