"""Report actual rest topology at suspicious posed triangles; no exclusions/acceptance."""
import bpy, json, sys
from pathlib import Path
source, audit_path, output = map(Path, sys.argv[sys.argv.index('--')+1:])
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(source))
audit = json.loads(audit_path.read_text()); records = []
for hand in audit['frame_records'][0]['hands']:
    obj = bpy.data.objects[hand['mesh']]; obj.data.calc_loop_triangles()
    triangles = obj.data.loop_triangles
    pairs = []
    for a, b in hand['first_nonadjacent_triangle_pairs']:
        va, vb = list(triangles[a].vertices), list(triangles[b].vertices)
        distances = sorted(((obj.data.vertices[i].co-obj.data.vertices[j].co).length, i, j) for i in va for j in vb)
        pairs.append({'triangles': [a,b], 'rest_nearest_vertex_distance_m': distances[0][0],
                      'rest_coincident_vertex_pairs_1e7': [(i,j) for d,i,j in distances if d < 1e-7],
                      'actual_triangle_vertices': [va,vb]})
    records.append({'mesh': obj.name, 'pairs': pairs})
output.write_text(json.dumps({'source': str(source), 'rest_topology_pairs': records, 'accepted': False},indent=2)+'\n')
print(json.dumps(records),flush=True)
