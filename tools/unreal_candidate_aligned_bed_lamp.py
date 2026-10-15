"""Compare the existing bedside emitter at its actual full-source glass bulb."""
import json,time,math
from pathlib import Path

def run():
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE
 from unreal_import_reference_entry import snapshot
 import unreal_candidate_visual_review as review
 assert active_candidate_guard(u.Paths.project_dir());proof=json.loads((CANDIDATE/'private-audit/bed-lamp-fullsource.json').read_text());glass=[r for r in proof['sections']if r['source_material'].endswith('_glass.SUB01_RealLamp_BedLamp_industrial_pipe_lamp_glass')]
 if not proof.get('original_untouched')or len(glass)!=1:raise RuntimeError('Actual full source existing glass bulb geometry required')
 center=glass[0]['bbox_center_cm'];radius=glass[0]['half_shortest_glass_extent_cm']*.5
 if not .2<=radius<=3 or math.dist(center,[-355,-303.79412174603203,379.9608406610787])>.05:raise RuntimeError('Measured real source bulb dimensions and saved placement must agree')
 eas=u.get_editor_subsystem(u.EditorActorSubsystem);actors=list(eas.get_all_level_actors());before=snapshot(u,actors);found=[a for a in actors if a.get_actor_label()=='SUB01_AuthoredLight_BedLamp'];assert len(found)==1;actor=found[0];cs=actor.get_components_by_class(u.PointLightComponent);assert len(cs)==1;light=cs[0]
 old_position=actor.get_actor_location();old={k:light.get_editor_property(k)for k in ['intensity','temperature','use_temperature','source_radius']}
 def state():return {'position':[float(getattr(actor.get_actor_location(),k))for k in('x','y','z')],**{k:str(light.get_editor_property(k))for k in old}}
 baseline=state();root=CANDIDATE/'evidence/aligned-bed-lamp'/str(time.time_ns());root.mkdir(parents=True);path=root/'comparison.json';report={'schema':'sub01.actual-candidate-aligned-bed-lamp-comparison.v1','only_existing_real_fixture':True,'actual_glass_source':glass[0]['source_material'],'actual_glass_bbox_center_cm':center,'finite_emitter_radius_cm':radius,'radius_method':'Equivalent finite emitter radius is half the shortest glass semiextent, bounded inside the real bulb; filament radius is not claimed measured.','baseline':baseline,'steps':[],'world_saved':False,'restored_prior_verified':False,'visual_acceptance':False}
 def persist():path.write_text(json.dumps(report,indent=2)+'\n')
 def restore():
  actor.set_actor_location(old_position,False,True)
  for k,v in old.items():light.set_editor_property(k,v)
  if state()!=baseline or snapshot(u,list(eas.get_all_level_actors()))!=before:raise RuntimeError('Exact original lamp and complete candidate world restoration required')
 def before_view(name):
  restore()
  if name.startswith('aligned-'):
   power,temp={'aligned-0p35cd-3000K':(.35,3000.),'aligned-0p7cd-3000K':(.7,3000.),'aligned-0p35cd-3500K':(.35,3500.)}[name];actor.set_actor_location(u.Vector(*center),False,True);light.set_editor_property('source_radius',radius);light.set_intensity(power);light.set_editor_property('temperature',temp);light.set_editor_property('use_temperature',True)
  report['steps'].append({'view':name,'actual_state':state()});persist()
 def finish(error):
  try:restore();assert active_candidate_guard(u.Paths.project_dir());report['restored_prior_verified']=True
  finally:report.update(error=error,finished_epoch=time.time());persist()
  return True
 pos=(-110,-80,465);rot=(-26,-128,0);views=[(n,pos,rot)for n in ['old-off-baseline','aligned-0p35cd-3000K','aligned-0p7cd-3000K','aligned-0p35cd-3500K','old-off-restored']];persist()
 try:r=review.run(views,capture_delay=15.,initial_delay=0.,before_view=before_view,on_finish=finish)
 except Exception:finish('Launch refused');raise
 report['capture_receipt']=r['receipt'];persist();return {'comparison':str(path),'capture_receipt':r['receipt'],'visual_acceptance':False,'world_saved':False}
