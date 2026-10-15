"""Source-only anatomical hand rig. Original CC0 surfaces, new bone-heat weights."""
import bpy,json,hashlib,math,collections,bmesh,sys
sys.path.insert(0,'/workspace/sub01-home-private/upright-footrest-python/scipy-1.14.1-cp311')
import numpy as np
from scipy.optimize import least_squares
from pathlib import Path
from mathutils import Vector
from mathutils.geometry import barycentric_transform
from mathutils.bvhtree import BVHTree
def robust_closest_bary(p,a,b,c):
 p,a,b,c=[tuple(float(x)for x in v)for v in[p,a,b,c]]
 sub=lambda a,b:tuple(x-y for x,y in zip(a,b));dot=lambda a,b:sum(x*y for x,y in zip(a,b))
 ab,ac,ap=sub(b,a),sub(c,a),sub(p,a);d1,d2=dot(ab,ap),dot(ac,ap)
 if d1<=0 and d2<=0:return(1.,0.,0.)
 bp=sub(p,b);d3,d4=dot(ab,bp),dot(ac,bp)
 if d3>=0 and d4<=d3:return(0.,1.,0.)
 vc=d1*d4-d3*d2
 if vc<=0 and d1>=0 and d3<=0:
  v=d1/(d1-d3);return(1-v,v,0.)
 cp=sub(p,c);d5,d6=dot(ab,cp),dot(ac,cp)
 if d6>=0 and d5<=d6:return(0.,0.,1.)
 vb=d5*d2-d1*d6
 if vb<=0 and d2>=0 and d6<=0:
  w=d2/(d2-d6);return(1-w,0.,w)
 va=d3*d6-d5*d4
 if va<=0 and d4-d3>=0 and d5-d6>=0:
  w=(d4-d3)/((d4-d3)+(d5-d6));return(0.,1-w,w)
 denom=va+vb+vc
 if denom==0:raise RuntimeError('Degenerate source heat triangle requires explicit cleanup')
 v,w=vb/denom,vc/denom;return(1-v-w,v,w)

root=Path('/workspace/sub01-home-private/human-base-hands-r1');source=root/'source/human-base-meshes-bundle-v1.4.1/human_base_meshes_bundle.blend';pair=root/'adult-hand-pair-source-r1/official-adult-hand-pair-unrigged.glb';out=root/'rig-r9';out.mkdir(exist_ok=False)
assert hashlib.sha256(pair.read_bytes()).hexdigest()=='dd355e9a42b0b3df69e932e57007c27ad8e2374066948c42ef5edeb1e2007a6e'
bpy.ops.wm.read_factory_settings(use_empty=True)
with bpy.data.libraries.load(str(source),link=False)as(src,dst):dst.objects=[n for n in src.objects if n.startswith('GEO-skeletion.')and any(k in n for k in ['metacarpal','proximal.','middle.','distal.','radius','ulna','skull'])]+['GEO-body_male_realistic']
anatomy={o.name:o for o in dst.objects}
for o in dst.objects:bpy.context.scene.collection.objects.link(o);o.hide_render=True;o.hide_set(True)
bpy.context.view_layer.update();body=anatomy['GEO-body_male_realistic'];bodypts=[body.matrix_world@v.co for v in body.data.vertices];bodyfloor=min(v.z for v in bodypts);bodyheight=max(v.z for v in bodypts)-bodyfloor
skeletonpoints=[o.matrix_world@v.co for n,o in anatomy.items()if n.startswith('GEO-skeletion.')for v in o.data.vertices];skeletalfloor=min(v.z for v in skeletonpoints);skeletalheight=max(v.z for v in skeletonpoints)-skeletalfloor
center=(anatomy['GEO-skeletion.metacarpal.middle.L'].matrix_world.translation.x+anatomy['GEO-skeletion.metacarpal.middle.R'].matrix_world.translation.x)*.5;scale=bodyheight/skeletalheight
print('SKELETAL_SOURCE_FIT',bodyfloor,bodyheight,skeletalfloor,skeletalheight,scale,flush=True)
def convert(p):return Vector(((p.x-center)*scale+body.matrix_world.translation.x,p.y*scale,(p.z-skeletalfloor)*scale+bodyfloor))
def origin(name):return convert(anatomy[name].matrix_world.translation)
def tip(name):
 o=anatomy[name];pts=[o.matrix_world@v.co for v in o.data.vertices];head=o.matrix_world.translation;far=max(pts,key=lambda p:(p-head).length);axis=(far-head).normalized();end=max((p-head).dot(axis)for p in pts);cap=[p for p in pts if(p-head).dot(axis)>end-.003];return convert(sum(cap,Vector())/len(cap))
bpy.ops.import_scene.gltf(filepath=str(pair));hands={side:bpy.data.objects['CC0Adult_'+side+'_ForearmHand_SOURCE_UNRIGGED']for side in ['Left','Right']};rigdata=bpy.data.armatures.new('CC0AnatomicalHandRig');rig=bpy.data.objects.new('CC0AnatomicalHandRig',rigdata);bpy.context.scene.collection.objects.link(rig);rig.show_in_front=True;rig.display_type='WIRE';sources={};landmarks={};trees={};original={}
for side,o in hands.items():
 o.hide_render=False;o.hide_set(False);bpy.context.view_layer.update();pts=[o.matrix_world@v.co for v in o.data.vertices];o.data.calc_loop_triangles();tree=BVHTree.FromPolygons(pts,[list(t.vertices)for t in o.data.loop_triangles],all_triangles=True,epsilon=0);trees[side]=tree;original[side]=[list(v.co)for v in o.data.vertices];lo=min(v.x for v in pts)-.1;hi=max(v.x for v in pts)+.1
 def medial(pred,label):
  choices=[]
  for radius in [0,.002,.004,.006,.008,.01,.012,.016]:
   for dy,dz in ([(0,0)]if radius==0 else [(radius,0),(-radius,0),(0,radius),(0,-radius),(radius*.707,radius*.707),(-radius*.707,radius*.707),(radius*.707,-radius*.707),(-radius*.707,-radius*.707)]):
    y,z=pred.y+dy,pred.z+dz;a=tree.ray_cast(Vector((lo,y,z)),Vector((1,0,0)));b=tree.ray_cast(Vector((hi,y,z)),Vector((-1,0,0)))
    if a[0]is not None and b[0]is not None:
     thickness=b[0].x-a[0].x
     if .003<thickness<.07:choices.append((math.hypot(dy,dz),Vector(((a[0].x+b[0].x)*.5,y,z)),thickness))
   if choices:break
  if not choices:raise RuntimeError('Actual hand crosssection missing for anatomical joint '+label+' '+str(list(pred)))
  distance,p,thickness=min(choices,key=lambda r:r[0]);landmarks[label]={'authored_anatomical_prediction':list(pred),'actual_skin_medial':list(p),'yz_search_distance_m':distance,'full_skin_crosssection_thickness_m':thickness,'x_medial_correction_m':p.x-pred.x};return p
 # Authoritative original sculpt regions, visually verified against actual nails.
 label_map={'Left':{'palm':9,'forearm':12,'Pinky':[64,65,66,67],'Ring':[68,69,70,71],'Middle':[72,73,74,75],'Index':[76,77,78,79],'Thumb':[80,81,82,83]},'Right':{'palm':10,'forearm':11,'Thumb':[84,85,86,87],'Index':[88,89,90,91],'Middle':[92,93,94,95],'Ring':[96,97,98,99],'Pinky':[100,101,102,103]}}[side]
 face_sets=body.data.attributes['.sculpt_face_set'];assert face_sets.domain=='FACE'and face_sets.data_type=='INT'
 region_vertices=collections.defaultdict(set)
 for face in body.data.polygons:region_vertices[face_sets.data[face.index].value].update(face.vertices)
 def authored_ring(a,b,label):
  ids=sorted(region_vertices[a]&region_vertices[b]);assert len(ids)>=3,('Actual shared authored boundary missing',side,a,b,len(ids))
  center=sum((body.matrix_world@body.data.vertices[i].co for i in ids),Vector())/len(ids);result=medial(center,label)
  assert landmarks[label]['yz_search_distance_m']<=.004,'Authored source boundary missed expected detailed skin'
  landmarks[label].update({'source_authority':'Original sculpt face-set shared boundary','source_face_set_ids':[a,b],'source_boundary_vertex_ids':ids,'source_boundary_world_centroid':list(center),'physical_digit':label})
  return result
 handpoints={}
 for finger in ['Thumb','Index','Middle','Ring','Pinky']:
  a,b,c,nail=label_map[finger]
  points=[authored_ring(label_map['palm'],a,side+finger+'1'),authored_ring(a,b,side+finger+'2'),authored_ring(b,c,side+finger+'3')]
  direction=(points[2]-points[1]).normalized();distal=[body.matrix_world@body.data.vertices[i].co for i in region_vertices[c]|region_vertices[nail]];furthest=max(v.dot(direction)for v in distal);cap=[v for v in distal if v.dot(direction)>furthest-.003];center=sum(cap,Vector())/len(cap);center=center.lerp(points[2],.07);end=medial(center,side+finger+'4');assert landmarks[side+finger+'4']['yz_search_distance_m']<=.004,'Actual sculpt fingertip missed its detailed digit'
  landmarks[side+finger+'4'].update({'source_authority':'Actual authored distal and nail regions, inward cap centroid','source_face_set_ids':[c,nail],'source_nail_face_set_id':nail,'source_cap_world_centroid':list(center),'physical_digit':finger})
  handpoints[finger]=points+[end]
 for finger in ['Thumb','Index','Middle','Ring','Pinky']:
  initial=np.array([list(v)for v in handpoints[finger]],dtype=float);lengths=np.linalg.norm(np.diff(initial,axis=0),axis=1)
  def signed(point):
   near,normal,_,dist=tree.find_nearest(Vector(point));assert near is not None
   return float((Vector(point)-near).dot(normal))
  def residual(x):
   points=initial+x.reshape(4,3)*.01;values=list(x*.03)
   values.extend((np.linalg.norm(np.diff(points,axis=0),axis=1)-lengths)/.01*.2)
   for segment in range(3):
    for t in np.linspace(0,1,13):values.append(max(0,signed(points[segment]*(1-t)+points[segment+1]*t)+.001)*10000)
   return np.array(values)
  def jac(x):
   columns=[];h=.002
   for i in range(len(x)):
    a=x.copy();b=x.copy();a[i]+=h;b[i]-=h;columns.append((residual(a)-residual(b))/(2*h))
   return np.column_stack(columns)
  fit=least_squares(residual,np.zeros(12),jac=jac,bounds=(-.35,.35),max_nfev=100,xtol=1e-7,ftol=1e-7,gtol=1e-7)
  refined=initial+fit.x.reshape(4,3)*.01;worst=max(signed(refined[k]*(1-t)+refined[k+1]*t)for k in range(3)for t in np.linspace(0,1,33));assert worst<-.0002,'Full segment anatomical fit failed '+side+finger+' '+str(worst)
  handpoints[finger]=[Vector(v)for v in refined];landmarks[side+finger+'_segment_fit']={'source_initial_points':initial.tolist(),'new_points':refined.tolist(),'maximum_joint_displacement_m':float(np.linalg.norm(refined-initial,axis=1).max()),'worst_signed_nearest_surface_clearance_m':worst,'actual_source_mesh_vertices_changed':False,'note':'Only anatomical joint placement fitted within original skin. Independent parity audit still required.'};print('CHAIN_FIT',side,finger,worst,flush=True)
 wrist=authored_ring(label_map['palm'],label_map['forearm'],side+'Hand');edges=collections.Counter(tuple(sorted((t.vertices[i],t.vertices[(i+1)%3])))for t in o.data.loop_triangles for i in range(3));boundary=sorted({i for e,count in edges.items()if count==1 for i in e});assert len(boundary)>10;elbow=sum((pts[i]for i in boundary),Vector())/len(boundary);boundary_center=elbow.copy();elbow+=(wrist-elbow).normalized()*.015;landmarks[side+'ForeArm']={'actual_open_forearm_boundary_centroid':list(boundary_center),'heat_rig_root_moved_inside_open_cuff_m':.015,'rig_root':list(elbow),'boundary_vertices':len(boundary),'role':'Truncated source forearm anchor under future cuff; not claimed anatomical elbow'};sources[side]={'fingers':handpoints,'wrist':wrist,'elbow':elbow}
bpy.ops.object.select_all(action='DESELECT');rig.select_set(True);bpy.context.view_layer.objects.active=rig;bpy.ops.object.mode_set(mode='EDIT')
for side,s in sources.items():
 def add(name,head,tail,parent=None,deform=True):
  b=rigdata.edit_bones.new('mixamorig:'+side+name);b.head=head;b.tail=tail
  if(b.tail-b.head).length<.001:b.tail=b.head+Vector((0,0,-.001))
  b.use_deform=deform;b.parent=parent;b.align_roll(Vector((1 if side=='Left'else-1,0,0)));return b
 fore=add('ForeArm',s['elbow'],s['wrist']);hand=add('Hand',s['wrist'],s['fingers']['Middle'][0],fore)
 for finger,pts in s['fingers'].items():
  parent=hand
  for i in range(3):parent=add('Hand'+finger+str(i+1),pts[i],pts[i+1],parent)
  add('Hand'+finger+'4',pts[3],pts[3]+(pts[3]-pts[2]).normalized()*.002,parent,False)
bpy.ops.object.mode_set(mode='OBJECT');weight_reports=[]
for side,o in hands.items():
 basepoints=[body.matrix_world@v.co for v in body.data.vertices];sign=1 if side=='Left'else-1;base_center=body.matrix_world.translation.x;eligible={i for i,v in enumerate(basepoints)if sign*(v.x-base_center)>.28 and bodyfloor+.5<v.z<bodyfloor+1.2};basefaces=[list(p.vertices)for p in body.data.polygons if any(i in eligible for i in p.vertices)];used=sorted({i for p in basefaces for i in p});remap={i:j for j,i in enumerate(used)};helperdata=bpy.data.meshes.new('OriginalCC0CoarseHeatDomain'+side);helperdata.from_pydata([basepoints[i]for i in used],[],[[remap[i]for i in p]for p in basefaces]);helperdata.update();helper=bpy.data.objects.new('TEMP_HEAT_SOLVER_'+side,helperdata);bpy.context.scene.collection.objects.link(helper);helper.hide_render=True;bm=bmesh.new();bm.from_mesh(helper.data);bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=1e-7);boundary=[e for e in bm.edges if e.is_boundary];boundary_count=len(boundary);bmesh.ops.holes_fill(bm,edges=boundary,sides=0);assert not any(e.is_boundary or not e.is_manifold for e in bm.edges),'Temporary heat domain is not closed/manifold';bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(helper.data);bm.free();helper.data.update();bpy.ops.object.select_all(action='DESELECT');helper.select_set(True);rig.select_set(True);bpy.context.view_layer.objects.active=rig
 # Only same-side bones participate in each source's heat solve; no old owner
 # weights, nearest-old-surface transfer, or hand-authored finger weighting.
 for b in rigdata.bones:b.use_deform=b.name.startswith('mixamorig:'+side)and not b.name.endswith('4')
 bpy.ops.object.parent_set(type='ARMATURE_AUTO');bpy.context.view_layer.update();assert len(helper.vertex_groups)>10
 helper.data.calc_loop_triangles();htris=[list(t.vertices)for t in helper.data.loop_triangles];hpts=[helper.matrix_world@v.co for v in helper.data.vertices];htree=BVHTree.FromPolygons(hpts,htris,all_triangles=True,epsilon=0)
 for group in helper.vertex_groups:o.vertex_groups.new(name=group.name)
 projection_max=0
 for v in o.data.vertices:
  p=o.matrix_world@v.co;point,normal,ti,distance=htree.find_nearest(p);assert point is not None and distance<.015,'Coarse/source sculpt correspondence exceeds15mm '+str(v.index)+' '+str(distance)+' '+str(list(p));projection_max=max(projection_max,distance);ids=htris[ti];coeff=robust_closest_bary(p,*[hpts[i]for i in ids]);weights={}
  for index,alpha in zip(ids,coeff):
   assert alpha>=-1e-4,'Invalid source-domain barycentric projection'
   for g in helper.data.vertices[index].groups:
    name=helper.vertex_groups[g.group].name;weights[name]=weights.get(name,0)+max(0,alpha)*g.weight
  total=sum(weights.values())
  if total>0:
   for name,weight in weights.items():
    if weight>1e-9:o.vertex_groups[name].add([v.index],weight/total,'REPLACE')
 o.parent=rig;mod=o.modifiers.new('New anatomical bone heat','ARMATURE');mod.object=rig;bpy.data.objects.remove(helper,do_unlink=True)
 zero=[];max_sum_error=0;wrong=[]
 for v in o.data.vertices:
  groups=[(o.vertex_groups[g.group].name,g.weight)for g in v.groups if g.weight>1e-8];total=sum(w for _,w in groups)
  if total<=0:zero.append(v.index)
  else:max_sum_error=max(max_sum_error,abs(total-1))
  if any(not n.startswith('mixamorig:'+side)for n,w in groups):wrong.append(v.index)
 diagnostic={'side':side,'zero_weights':len(zero),'wrong_side_weights':len(wrong),'groups':{g.name:sum(any(q.group==g.index and q.weight>1e-8 for q in v.groups)for v in o.data.vertices)for g in o.vertex_groups},'landmarks':landmarks,'bones':[{'name':b.name,'head':list(b.head_local),'tail':list(b.tail_local),'length':b.length,'deform':b.use_deform}for b in rigdata.bones]};(out/'heat-diagnostic.json').write_text(json.dumps(diagnostic,indent=2)+'\n');bpy.ops.wm.save_as_mainfile(filepath=str(out/'FAILED_OR_PENDING_NOT_ACCEPTED.blend'));print('HEAT_DIAGNOSTIC',side,len(zero),len(wrong),diagnostic['groups'],flush=True);assert not zero and not wrong,'Heat weights missing or cross-side';assert max_sum_error<1e-4
 assert all((v.co-Vector(original[side][i])).length==0 for i,v in enumerate(o.data.vertices)),'Binding changed source vertex geometry'
 weight_reports.append({'side':side,'vertices':len(o.data.vertices),'zero_weight_vertices':len(zero),'cross_side_influence_vertices':len(wrong),'max_weight_sum_error':max_sum_error,'original_coarse_heat_vertices':len(used),'maximum_source_projection_distance_m':projection_max,'temporary_heat_domain_boundary_edges_closed':boundary_count,'temporary_solver_caps_exported':False,'method':'Blender ARMATURE_AUTO bone heat on original coarse-quad source helper with temporary closed forearm domain; barycentric new-heat weights transferred onto unchanged sculpt vertices, no old owner weights'})
for b in rigdata.bones:b.use_deform=not b.name.endswith('4')
# A genuine articulable rest rig is saved before any motion adaptation.
bpy.ops.object.select_all(action='DESELECT');rig.select_set(True)
for o in hands.values():o.select_set(True)
bpy.context.view_layer.objects.active=rig
bpy.ops.wm.save_as_mainfile(filepath=str(out/'official-adult-hand-pair-rig.blend'))
bpy.ops.export_scene.gltf(filepath=str(out/'official-adult-hand-pair-rig.glb'),export_format='GLB',use_selection=True,export_animations=False,export_skins=True,export_all_influences=True)
report={'schema':'sub01.anatomical-hand-rig.v2','source_pair_sha256':hashlib.sha256(pair.read_bytes()).hexdigest(),'rig_glb_sha256':hashlib.sha256((out/'official-adult-hand-pair-rig.glb').read_bytes()).hexdigest(),'rig_blend':str(out/'official-adult-hand-pair-rig.blend'),'source_skeleton_height_scale':scale,'source_mesh_vertices_unchanged':True,'new_bones':[{'name':b.name,'head':list(b.head_local),'tail':list(b.tail_local),'rest_matrix_rows':[list(r)for r in b.matrix_local],'deform':b.use_deform}for b in rigdata.bones],'landmarks':landmarks,'weights':weight_reports,'cuff_seam_fit_verified':False,'deformation_or_contact_verified':False,'native_imported':False,'visual_accepted':False};(out/'rig-report.json').write_text(json.dumps(report,indent=2)+'\n');print('ACTUAL_ANATOMICAL_HAND_RIG_BUILT',json.dumps({'sha256':report['rig_glb_sha256'],'weights':weight_reports,'bones':len(rigdata.bones)}),flush=True)
