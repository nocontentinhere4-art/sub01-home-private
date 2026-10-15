"""Independent full written GLB corner comparison against official sculpt."""
import bpy,json,struct,collections,hashlib
from pathlib import Path
root=Path('/workspace/sub01-home-private/human-base-hands-r1');source=root/'source/human-base-meshes-bundle-v1.4.1/human_base_meshes_bundle.blend';target=root/'adult-hand-pair-source-r1/official-adult-hand-pair-unrigged.glb';raw=target.read_bytes();n=struct.unpack_from('<I',raw,12)[0];doc=json.loads(raw[20:20+n]);blob=raw[28+n:]
def acc(i):
 a=doc['accessors'][i];v=doc['bufferViews'][a['bufferView']];assert not v.get('extensions')and not a.get('sparse');count={'SCALAR':1,'VEC3':3}[a['type']];fmt={5126:'f',5125:'I',5123:'H',5121:'B'}[a['componentType']];size=struct.calcsize('<'+fmt*count);return [struct.unpack_from('<'+fmt*count,blob,v.get('byteOffset',0)+a.get('byteOffset',0)+j*v.get('byteStride',size))for j in range(a['count'])]
bpy.ops.wm.read_factory_settings(use_empty=True)
with bpy.data.libraries.load(str(source),link=False)as(s,d):d.objects=['GEO-body_male_realistic']
o=d.objects[0];bpy.context.scene.collection.objects.link(o)
for m in o.modifiers:m.levels=m.total_levels
bpy.context.view_layer.update();evaluated=o.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=evaluated.to_mesh();mesh.calc_loop_triangles();world=[o.matrix_world@v.co for v in mesh.vertices];center=(min(v.x for v in world)+max(v.x for v in world))*.5;floor=min(v.z for v in world);rows=[]
# Integer coordinates at0.0001mm resolve only binary rounding; each complete
# original triangle is retained, no fitted registration or geometry alignment.
def key(v):return tuple(round(float(x)*1e7)for x in v)
for side,sign in [('Left',1),('Right',-1)]:
 expected=collections.Counter(tuple(sorted(key((world[i].x,world[i].z,-world[i].y))for i in t.vertices))for t in mesh.loop_triangles if all(sign*(world[i].x-center)>.28 and floor+.5<world[i].z<floor+1.2 for i in t.vertices));node=next(n for n in doc['nodes']if n.get('name')=='CC0Adult_'+side+'_ForearmHand_SOURCE_UNRIGGED');assert not any(k in node for k in['matrix','translation','rotation','scale']);actual=collections.Counter()
 for pr in doc['meshes'][node['mesh']]['primitives']:
  pts=acc(pr['attributes']['POSITION']);idx=[v[0]for v in acc(pr['indices'])]
  for j in range(0,len(idx),3):actual[tuple(sorted(key(pts[i])for i in idx[j:j+3]))]+=1
 assert actual==expected,'Official source surface corner mismatch '+side
 rows.append({'side':side,'written_positive_or_zero_triangles':sum(actual.values()),'all_triangle_corners_bijective_with_official_source':True,'coordinate_quantum_m':1e-7,'source_geometry_fitting':False,'mirroring':False})
report={'schema':'sub01.official-human-hand-pair-roundtrip.v1','official_blend_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'written_pair_sha256':hashlib.sha256(raw).hexdigest(),'rows':rows,'source_only':True,'rig_or_weights_ready':False,'native_imported':False,'visual_or_contact_accepted':False};(target.parent/'independent-written-surface-proof.json').write_text(json.dumps(report,indent=2)+'\n');print('OFFICIAL_HAND_PAIR_ROUNDTRIP_PROOF',json.dumps(report),flush=True)
