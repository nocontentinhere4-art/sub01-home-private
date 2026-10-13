import argparse,json,sys
from pathlib import Path
import numpy as np,trimesh
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from home_world import HomeWorld
parser=argparse.ArgumentParser(description='Check real sofa/backrest triangles and continuous standing routes against an exported private house.')
parser.add_argument('--source',type=Path,default=ROOT/'out/lighting-v19/source.glb')
parser.add_argument('--output',type=Path,help='Optional JSON evidence path')
args=parser.parse_args()
if not args.source.is_file():parser.error('Source export does not exist; export the current private scene or pass --source')
scene=trimesh.load(args.source,force='scene');groups={'sofa':[],'table':[]}
for node in scene.graph.nodes_geometry:
    group='sofa' if node.startswith('Haven_') else 'table' if node=='Oak_coffee_table' else None
    if not group:continue
    matrix,name=scene.graph[node];m=scene.geometry[name];v=trimesh.transform_points(m.vertices,matrix);groups[group].append(v[m.faces])
tri={k:np.concatenate(v) for k,v in groups.items()}
bounds={k:[v.min(axis=(0,1)).tolist(),v.max(axis=(0,1)).tolist()] for k,v in tri.items()}
def segment_hits(p,q,triangles):
    p=np.array(p);direction=np.array(q)-p;e1=triangles[:,1]-triangles[:,0];e2=triangles[:,2]-triangles[:,0]
    cross=np.cross(direction,e2);det=(e1*cross).sum(axis=1);valid=np.abs(det)>1e-9;inv=np.zeros_like(det);inv[valid]=1/det[valid]
    delta=p-triangles[:,0];u=(delta*cross).sum(axis=1)*inv;r=np.cross(delta,e1);v=(r*direction).sum(axis=1)*inv;t=(r*e2).sum(axis=1)*inv
    valid&=(u>=0)&(v>=0)&(u+v<=1)&(t>.02)&(t<1)
    return [(p+direction*n).tolist() for n in t[valid]]
# Pelvis centre surrogate calibrated to the measured .503m seat and retained
# .8625m seated eye-to-seat distance. Seated contact itself is intentional.
seat=[-1.8,.503,.1]
old_hits=segment_hits(seat,[-.45,.7875,.1],tri['sofa'])
new_hits=segment_hits(seat,[-2.55,.7875,.1],tri['sofa'])
assert old_hits,'Old get-up trajectory intersects real couch back triangles'
assert not new_hits,'New forward get-up trajectory clears real couch triangles after initial seat contact'

home=HomeWorld({'node':'desk','seated':1});trace=[]
for activity in ['play_console','park','play_console','research']:
    for _ in range(4000):
        home.update(.02,.02,{'activity':activity},{})
        trace.append({'position':home.position[:],'eye':home.view()['position'],'seated':home.seated,'node':home.node,'activity':activity})
        if home.activity_ready(activity):break
    assert home.activity_ready(activity)
def sweep_overlaps(a,b,lo,hi):
    # Conservative swept vertical capsule: its x/z projection is contained
    # by a .16m-expanded furniture box. Disjointness proves no triangle touch
    # on the complete segment, not just at sampled endpoints.
    t0,t1=0.,1.
    for axis in [0,2]:
        start=a[axis];delta=b[axis]-start;low=lo[axis]-.16;high=hi[axis]+.16
        if abs(delta)<1e-10:
            if not low<start<high:return False
        else:
            enter,exit=sorted([(low-start)/delta,(high-start)/delta]);t0=max(t0,enter);t1=min(t1,exit)
            if t0>=t1:return False
    return True
checked=0
for previous,current in zip(trace,trace[1:]):
    if previous['seated'] or current['seated']:continue
    checked+=1
    for name,(lo,hi) in bounds.items():
        assert not sweep_overlaps(previous['position'],current['position'],lo,hi),(name,previous,current)
seat_eyes=[row['eye'] for row in trace if row['node']=='sofa']
minimum_eye=min(p[1] for p in seat_eyes)
assert minimum_eye-.04>bounds['sofa'][1][1],'Eye near plane stays above actual back throughout sit/stand'
report={'source':str(args.source),'actual_world_bounds':bounds,'old_pelvis_backrest_triangle_hits':old_hits,'new_forward_pelvis_triangle_hits':new_hits,'pelvis_model':'Seat .503m plus existing eye-seat offset .8625m; surrogate proves back crossing, not full seated anatomy','continuous_standing_segments_proved_clear_of_actual_furniture_bounds':checked,'body_radius':.16,'seat_transition_min_eye':minimum_eye,'actual_backrest_max_height':bounds['sofa'][1][1],'scope':'Only sofa and coffee-table geometry; intentional seat/pelvis contact excluded from standing capsule clearance, no full-body seated claim'}
if args.output:
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
