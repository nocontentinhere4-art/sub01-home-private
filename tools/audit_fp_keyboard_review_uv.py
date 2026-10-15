"""Read-only actual FBX triangle/UV bijection; no renderer/world changes."""
import hashlib,json,sys,time
from pathlib import Path


def run(out):
 import bpy,numpy as np
 from scipy.spatial import cKDTree
 from scipy.sparse import csr_matrix
 from scipy.sparse.csgraph import maximum_bipartite_matching
 root=Path('/workspace/sub01-home-private/fp-keyboard-review-fbx-r5');out=Path(out);out.mkdir(exist_ok=False);began=time.monotonic()
 fbx=root/'FirstPersonKeyboardReview.fbx';assert hashlib.sha256(fbx.read_bytes()).hexdigest()=='07baf00adbe6e9fa49f22ea954787e3590ba602a5c7ab6f247cc990a50205d53'
 def geometry(obj):
  bpy.context.view_layer.update();evaluated=obj.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=evaluated.to_mesh();mesh.calc_loop_triangles();points=np.asarray([tuple(evaluated.matrix_world@v.co)for v in mesh.vertices]);faces=np.asarray([t.vertices for t in mesh.loop_triangles],int);uv=np.asarray([[tuple(mesh.uv_layers.active.data[i].uv)for i in t.loops]for t in mesh.loop_triangles]);tri=points[faces];evaluated.to_mesh_clear();return tri,uv
 bpy.ops.wm.open_mainfile(filepath=str(root/'first-person-keyboard-review.blend'));scene=bpy.context.scene;scene.frame_set(0);meshes=[o for o in scene.objects if o.type=='MESH'and any(m.type=='ARMATURE'for m in o.modifiers)];assert len(meshes)==1;reference,uv=geometry(meshes[0]);source_materials=[m.name for m in meshes[0].data.materials]
 bpy.ops.wm.read_factory_settings(use_empty=True);bpy.context.scene.render.fps=120;bpy.ops.import_scene.fbx(filepath=str(fbx),use_anim=True);bpy.context.scene.frame_set(1);meshes=[o for o in bpy.context.scene.objects if o.type=='MESH'];assert len(meshes)==1;actual,actual_uv=geometry(meshes[0]);assert len(reference)==len(actual)==88592
 # Full bipartite triangle matching: equal counts and every source/target used once.
 # UV is checked on the SAME corner permutation as the deformed source position.
 _,which=cKDTree(reference.mean(1)).query(actual.mean(1),k=16,workers=1);candidates=reference[which];candidate_uv=uv[which];valid=np.zeros(which.shape,bool);bestpos=np.full(len(actual),np.inf);bestuv=np.full(len(actual),np.inf)
 for permutation in ((0,1,2),(0,2,1),(1,0,2),(1,2,0),(2,0,1),(2,1,0)):
  p=np.linalg.norm(candidates[:,:,permutation,:]-actual[:,None,:,:],axis=-1).max(-1);v=np.abs(candidate_uv[:,:,permutation,:]-actual_uv[:,None,:,:]).max((-1,-2));ok=(p<=.0002)&(v<=1e-6);valid|=ok;bestpos=np.minimum(bestpos,np.where(v<=1e-6,p,np.inf).min(1));bestuv=np.minimum(bestuv,np.where(p<=.0002,v,np.inf).min(1))
 rows,columns=np.nonzero(valid);graph=csr_matrix((np.ones(len(rows),dtype=np.int8),(rows,which[rows,columns])),shape=(len(actual),len(reference)));matching=maximum_bipartite_matching(graph,perm_type='column');matched=int((matching>=0).sum());assert matched==88592,(matched,88592)
 result={'schema':'sub01.fp-keyboard-review-fbx-uv.v1','fbx_sha256':hashlib.sha256(fbx.read_bytes()).hexdigest(),'triangles':88592,'one_to_one_position_AND_UV_triangle_matches':matched,'all_source_and_target_triangles_used_once':True,'position_tolerance_cm':.02,'uv_tolerance':1e-6,'max_nearest_valid_position_error_cm':float(bestpos.max()*100),'max_nearest_valid_uv_error':float(bestuv.max()),'source_material_slots':source_materials,'FBX_material_slots':[m.name for m in meshes[0].data.materials],'native_material_policy':'Reuse exact existing original owner material; FBX shader conversion is not native PBR proof','source_glb_original_UV_PBR_accessors_unchanged':'See source arms index-only manifest and mergedGLB accessor hash audit; no texture edits','elapsed_s':time.monotonic()-began,'source_ready':False,'native_ready':False,'activity_ready':False};(out/'uv-roundtrip.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)

if __name__=='__main__':
 sys.path.insert(0,'/workspace/sub01-home-private/upright-footrest-python/scipy-1.14.1-cp311');run(sys.argv[sys.argv.index('--')+1])
