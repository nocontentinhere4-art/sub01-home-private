"""Runpod-only full evaluated original shoe skin audit, independent of IK proxies."""
import argparse, hashlib, json, math, sys
from pathlib import Path
import bpy
from mathutils import Vector

def main():
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('sha256');p.add_argument('contacts',type=Path);p.add_argument('output',type=Path)
    args=p.parse_args(sys.argv[sys.argv.index('--')+1:]);assert hashlib.sha256(args.source.read_bytes()).hexdigest()==args.sha256
    contacts=json.loads(args.contacts.read_text());fps=contacts['fps'];count=len(contacts['contacts']);assert 1<=fps<=120 and 10<=count<=900
    bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene;scene.render.fps=fps;bpy.ops.import_scene.gltf(filepath=str(args.source))
    arm=next(o for o in scene.objects if o.type=='ARMATURE');assert len(arm.data.bones)==65;arm.animation_data_create();arm.animation_data.action=list(bpy.data.actions)[0]
    for track in arm.animation_data.nla_tracks:track.mute=True
    start,end=arm.animation_data.action.frame_range;assert abs(start)<.001 and abs(end-(count-1))<.001
    selection={s:[] for s in ['Left','Right']}
    for o in scene.objects:
        if o.type!='MESH':continue
        for side in selection:
            groups={g.index for g in o.vertex_groups if g.name in [f'mixamorig:{side}{n}' for n in ['Foot','ToeBase','Toe_End']]}
            indices=[v.index for v in o.data.vertices if sum(g.weight for g in v.groups if g.group in groups)>.5]
            if indices:selection[side].append((o,indices))
    assert all(selection.values());graph=bpy.context.evaluated_depsgraph_get();records=[]
    for frame in range(count):
        scene.frame_set(frame);bpy.context.view_layer.update();row={'frame':frame,'time_s':frame/fps,'feet':{}}
        for side,parts in selection.items():
            low=math.inf
            for o,indices in parts:
                evaluated=o.evaluated_get(graph);mesh=evaluated.to_mesh();low=min(low,min((evaluated.matrix_world@mesh.vertices[i].co).z for i in indices));evaluated.to_mesh_clear()
            joints={n:arm.matrix_world@arm.pose.bones[f'mixamorig:{side}{n}'].head for n in ['UpLeg','Leg','Foot']}
            offset=0 if side=='Left' else 3
            row['feet'][side]={'minimum_actual_skin_z_m':low,'stance':any(contacts['contacts'][frame][offset:offset+3]),'thigh_m':(joints['Leg']-joints['UpLeg']).length,'calf_m':(joints['Foot']-joints['Leg']).length}
        records.append(row)
    summary={}
    for side in selection:
        stance=[r['feet'][side]['minimum_actual_skin_z_m'] for r in records if r['feet'][side]['stance']];swing=[r['feet'][side]['minimum_actual_skin_z_m'] for r in records if not r['feet'][side]['stance']]
        summary[side]={'stance_frames':len(stance),'stance_minima_range_m':[min(stance),max(stance)],'swing_minima_range_m':[min(swing),max(swing)] if swing else None,'joint_length_ranges_m':{k:[min(r['feet'][side][k] for r in records),max(r['feet'][side][k] for r in records)] for k in ['thigh_m','calf_m']}}
    passed=all(max(abs(v) for v in s['stance_minima_range_m'])<.00005 and (s['swing_minima_range_m'] is None or s['swing_minima_range_m'][0]>=.0029) and all(b-a<.00001 for a,b in s['joint_length_ranges_m'].values()) for s in summary.values())
    report={'schema':'sub01.independent-full-owner-skin-support.v1','candidate_sha256':args.sha256,'contact_sha256':hashlib.sha256(args.contacts.read_bytes()).hexdigest(),'frames':count,'fps':fps,'model_floor_z_m':0,'summary':summary,'records':records,'source_kinematic_gate_passed':passed,'all_skin_source_vertices_evaluated':True,'native_changed':False,'native_contact_accepted':False,'visual_accepted':False}
    args.output.write_text(json.dumps(report,indent=2)+'\n');print('ACTUAL_FULL_SKIN_SUPPORT',json.dumps({k:v for k,v in report.items() if k!='records'}),flush=True);assert passed,'Actual full-skin source contact gate failed'

if __name__=='__main__':main()
