"""Constrain digit influences with exact original sculpt regions, fading at shared boundaries."""
import bpy, hashlib, heapq, json, math, sys
from pathlib import Path
source, region_path, output = map(Path, sys.argv[sys.argv.index('--')+1:])
mapping = json.loads(region_path.read_text())
assert hashlib.sha256(region_path.read_bytes()).hexdigest() == '53aaed6944200e96ad24384f12ffdba609842f0f5d879c2f274636c32a62d760'
output.mkdir(exist_ok=False, parents=True)
bpy.ops.wm.open_mainfile(filepath=str(source))
rig = bpy.data.objects['CC0AnatomicalHandRig']
digit_labels = {'Left': {'Thumb':80,'Index':76,'Middle':72,'Ring':68,'Pinky':64},
                'Right': {'Thumb':84,'Index':88,'Middle':92,'Ring':96,'Pinky':100}}
report = {'source_blend_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
          'authored_region_map_sha256':hashlib.sha256(region_path.read_bytes()).hexdigest(),
          'transition_surface_geodesic_m':.008,'geometry_rest_or_pose_changed':False,
          'motion_contact_accepted':False,'sides':{}}
for side, label_map in digit_labels.items():
    obj = bpy.data.objects['CC0Adult_'+side+'_ForearmHand_SOURCE_UNRIGGED']
    points = [obj.matrix_world@v.co for v in obj.data.vertices]
    coordinates = [tuple(v.co)for v in obj.data.vertices]
    rows = mapping['sides'][side]['rows']; assert len(rows)==len(points)
    labels = {}
    for row in rows:
        i=row['rig_blend_vertex']; p=points[i]
        assert tuple(round(x/1e-7)for x in p)==tuple(row['source_world_coordinate_key'])
        labels[i]=set(row['source_face_set_ids'])
    adjacency=[[]for _ in points]
    for e in obj.data.edges:
        a,b=e.vertices; distance=(points[a]-points[b]).length
        adjacency[a].append((b,distance));adjacency[b].append((a,distance))
    records=[]
    for digit, base in label_map.items():
        region=set(range(base,base+4))
        inside={i for i,ids in labels.items()if ids and ids<=region}
        boundary={i for i in inside if any(j not in inside for j,_ in adjacency[i])}
        assert inside and boundary
        distance={i:0. for i in boundary}; queue=[(0.,i)for i in boundary];heapq.heapify(queue)
        while queue:
            d,i=heapq.heappop(queue)
            if d!=distance[i]:continue
            for j,length in adjacency[i]:
                if j not in inside:continue
                candidate=d+length
                if candidate<distance.get(j,math.inf):distance[j]=candidate;heapq.heappush(queue,(candidate,j))
        assert len(distance)==len(inside)
        foreign={f'mixamorig:{side}Hand{other}{n}'for other in label_map if other!=digit for n in(1,2,3)}
        own={f'mixamorig:{side}Hand{digit}{n}'for n in(1,2,3)}
        changed=0; before_total=after_total=0.
        for i in inside:
            v=obj.data.vertices[i]; weights={obj.vertex_groups[g.group].name:g.weight for g in v.groups}
            before=sum(w for n,w in weights.items()if n in foreign);before_total+=before
            t=min(1.,distance[i]/.008); fade=t*t*(3-2*t)
            if before>1e-8 and fade>0:
                assert sum(w for n,w in weights.items()if n in own)>.01,(side,digit,i)
                weights={n:w*(1-fade)if n in foreign else w for n,w in weights.items()}
                total=sum(weights.values());assert total>.05
                for n,w in weights.items():obj.vertex_groups[n].add([i],w/total,'REPLACE')
                changed+=1
            after_total+=sum(g.weight for g in v.groups if obj.vertex_groups[g.group].name in foreign)
        records.append({'digit':digit,'authored_regions':sorted(region),'exclusive_vertices':len(inside),
                        'boundary_vertices':len(boundary),'changed_vertices':changed,
                        'foreign_weight_sum_before':before_total,'foreign_weight_sum_after':after_total})
    assert coordinates==[tuple(v.co)for v in obj.data.vertices]
    error=max(abs(sum(g.weight for g in v.groups)-1)for v in obj.data.vertices);assert error<1e-6
    report['sides'][side]={'digits':records,'max_weight_sum_error':error}
bpy.ops.wm.save_as_mainfile(filepath=str(output/'official-adult-hand-pair-rig.blend'))
bpy.ops.object.select_all(action='DESELECT');rig.select_set(True)
for side in digit_labels:bpy.data.objects['CC0Adult_'+side+'_ForearmHand_SOURCE_UNRIGGED'].select_set(True)
bpy.context.view_layer.objects.active=rig
glb=output/'official-adult-hand-pair-rig.glb'
bpy.ops.export_scene.gltf(filepath=str(glb),export_format='GLB',use_selection=True,export_animations=False,export_skins=True,export_yup=True)
report['output_glb_sha256']=hashlib.sha256(glb.read_bytes()).hexdigest()
(output/'authored-weight-cleanup-report.json').write_text(json.dumps(report,indent=2)+'\n')
print('AUTHORED_REGION_DIGIT_WEIGHT_CLEANUP',json.dumps(report),flush=True)
