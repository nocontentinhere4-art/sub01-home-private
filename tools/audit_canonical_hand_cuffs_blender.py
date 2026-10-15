"""Independent original digit preservation in actual canonical fitted source."""
import bpy,json,math
from pathlib import Path
from mathutils import Matrix,Vector
R=Path('/workspace/sub01-home-private/human-base-hands-r1');p=R/'canonical-hand-cuffs-r1';report=json.loads((p/'canonical-source-report.json').read_text());bpy.ops.wm.open_mainfile(filepath=str(R/'rig-r9/uv-skin-source-r1/official-hand-uv-material-source.blend'));original={}
for side in ['Left','Right']:
 o=bpy.data.objects['CC0Adult_'+side+'_ForearmHand_SOURCE_UNRIGGED'];a=o.data.attributes['OriginalSculptFaceSet'];ids=set(range(64,84))if side=='Left'else set(range(84,104));indices={v for face in o.data.polygons if a.data[face.index].value in ids for v in face.vertices};original[side]=[v.co.copy()for v in o.data.vertices if v.index in indices]
bpy.ops.wm.open_mainfile(filepath=str(p/'canonical-anatomical-hand-cuffs.blend'));rows=[]
for side in ['Left','Right']:
 r=next(x for x in report['records']if x['side']==side);matrix=Matrix(r['canonical_rigid_fit_matrix']);o=bpy.data.objects['CC0Adult_'+side+'_ForearmHand_SOURCE_UNRIGGED'];assert max(abs(o.matrix_world[i][j]-(1 if i==j else 0))for i in range(4)for j in range(4))<1e-7
 # KDTree works in actual exported canonical metre space, independent of vertex order.
 from mathutils.kdtree import KDTree
 tree=KDTree(len(o.data.vertices))
 for v in o.data.vertices:tree.insert(v.co,v.index)
 tree.balance();maximum=0
 for point in original[side]:maximum=max(maximum,tree.find(matrix@point)[2])
 assert maximum<1e-6,('Genuine source digit geometry changed/cut',side,maximum)
 rows.append({'side':side,'authored_original_digit_vertices':len(original[side]),'max_canonical_rigid_surface_error_m':maximum,'same_both_anatomical_sides_not_mirrored':True})
result={'schema':'sub01.independent-canonical-genuine-digit-preservation.v1','sides':rows,'all_original_authored_digit_geometry_retained':True,'geometry_scale':1,'source_mesh_space':'physical metres, Blender Zup; export glTF Yup','self_contact_verified':False,'cuff_or_prop_contact_verified':False,'native_accepted':False};(p/'independent-digit-preservation-proof.json').write_text(json.dumps(result,indent=2));print('CANONICAL_DIGIT_GEOMETRY_PROOF',json.dumps(result),flush=True)
