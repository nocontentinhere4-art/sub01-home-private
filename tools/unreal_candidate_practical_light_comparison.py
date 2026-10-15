"""Bounded actual-fixture comparison, restoring all lights/exposure exactly.

No new/fill light, camera input, Game, actor transform, material or map save.
Each image changes one declared variable; histogram headroom is a separate view.
"""
import hashlib,json,os,re,time
from pathlib import Path

def semantic(value):return re.sub(r'\(0x[0-9a-fA-F]+\)','',str(value))
def run(refinement=False):
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE
 from unreal_import_reference_entry import snapshot
 import unreal_candidate_visual_review as review
 assert active_candidate_guard(u.Paths.project_dir());eas=u.get_editor_subsystem(u.EditorActorSubsystem);actors=list(eas.get_all_level_actors());before=snapshot(u,actors)
 def exact(label,cls):
  found=[a for a in actors if a.get_actor_label()==label];assert len(found)==1
  components=found[0].get_components_by_class(cls);assert len(components)==1
  return found[0],components[0]
 bed_actor,bed=exact('SUB01_AuthoredLight_BedLamp',u.LightComponent);bath_actor,bath=exact('SUB01_AuthoredLight_BathroomCeiling',u.LightComponent)
 volumes=[a for a in actors if a.get_actor_label()=='SUB01_ReferencePost'];assert len(volumes)==1;post=volumes[0]
 def state():
  return {'bed_intensity':float(bed.get_editor_property('intensity')),'bed_temperature':float(bed.get_editor_property('temperature')),'bed_temperature_enabled':bool(bed.get_editor_property('use_temperature')),'bath_intensity':float(bath.get_editor_property('intensity')),'bath_temperature':float(bath.get_editor_property('temperature')),'bath_temperature_enabled':bool(bath.get_editor_property('use_temperature')),'post':semantic(post.get_editor_property('settings'))}
 baseline=state();settings=post.get_editor_property('settings');min_ev=float(settings.get_editor_property('auto_exposure_min_brightness'))
 if baseline['bed_intensity']!=0 or baseline['bed_temperature']!=2700 or baseline['bath_intensity']!=5.5 or baseline['bath_temperature']!=3000 or not baseline['bath_temperature_enabled']or min_ev!=-3 or not settings.get_editor_property('override_auto_exposure_min_brightness'):raise RuntimeError('Exact actually measured original fixture/exposure baseline required')
 root=CANDIDATE/'evidence/practical-light-comparison'/str(time.time_ns());root.mkdir(parents=True);path=root/'comparison.json'
 report={'schema':'sub01.actual-candidate-practical-light-comparison.v1','editor_pid':os.getpid(),'started_epoch':time.time(),'bed_light':bed.get_path_name(),'bath_light':bath.get_path_name(),'existing_lights_only':True,'new_lights':0,'baseline':baseline,'baseline_min_ev100':min_ev,'steps':[],'world_saved':False,'live_game_or_input_changed':False,'restored_prior_verified':False,'visual_acceptance':False,'refinement':refinement,'actual_bed_fixture':{'class':bed.get_class().get_name(),'location':str(bed.get_world_location()),'rotation':str(bed.get_world_rotation()),'settings':{k:str(bed.get_editor_property(k))for k in ('intensity_units','attenuation_radius','source_radius','source_length','soft_source_radius')if hasattr(bed,k)}}}
 def persist():path.write_text(json.dumps(report,indent=2)+'\n')
 def restore():
  bed.set_intensity(baseline['bed_intensity']);bed.set_editor_property('temperature',baseline['bed_temperature']);bed.set_editor_property('use_temperature',baseline['bed_temperature_enabled']);bath.set_intensity(baseline['bath_intensity']);bath.set_editor_property('temperature',baseline['bath_temperature']);bath.set_editor_property('use_temperature',baseline['bath_temperature_enabled']);s=post.get_editor_property('settings');s.set_editor_property('auto_exposure_min_brightness',min_ev);post.set_editor_property('settings',s)
  if state()!=baseline or snapshot(u,list(eas.get_all_level_actors()))!=before:raise RuntimeError('Complete exact original light/exposure/actor snapshot restoration required')
 def before_view(name):
  assert active_candidate_guard(u.Paths.project_dir());restore();changed={}
  if name in ('bed-lamp-0p35cd-3000K','bed-lamp-0p7cd-3000K','bed-lamp-0p35cd-3500K'):
   intensity,temperature={'bed-lamp-0p35cd-3000K':(.35,3000.),'bed-lamp-0p7cd-3000K':(.7,3000.),'bed-lamp-0p35cd-3500K':(.35,3500.)}[name];bed.set_intensity(intensity);bed.set_editor_property('temperature',temperature);bed.set_editor_property('use_temperature',True);changed={'existing_bedside_lamp_candela':intensity,'existing_bedside_lamp_temperature_K':temperature}
  elif name=='bed-existing-lamp-3p5cd':bed.set_intensity(3.5);changed={'existing_bedside_lamp_candela':3.5}
  elif name=='bath-existing-lamp-4000K':bath.set_editor_property('temperature',4000.);changed={'existing_bathroom_fixture_temperature_K':4000.}
  elif name=='bed-exposure-only-minus4EV':s=post.get_editor_property('settings');s.set_editor_property('auto_exposure_min_brightness',-4.);post.set_editor_property('settings',s);changed={'minimum_histogram_EV100':-4.}
  report['steps'].append({'view':name,'only_changed':changed,'actual_state':state()});persist()
 def finish(error):
  try:restore();assert active_candidate_guard(u.Paths.project_dir());report['restored_prior_verified']=True
  finally:report.update(finished_epoch=time.time(),error=error);persist()
  return True
 bed_view=((-110,-80,465),(-26,-128,0));bath_view=((-230,120,465),(-22,123,0))
 views=[('bed-baseline',*bed_view),('bed-existing-lamp-3p5cd',*bed_view),('bath-baseline-3000K',*bath_view),('bath-existing-lamp-4000K',*bath_view),('bed-exposure-only-minus4EV',*bed_view),('bed-restored-baseline',*bed_view)]
 if refinement:views=[('bed-refinement-baseline',*bed_view),('bed-lamp-0p35cd-3000K',*bed_view),('bed-lamp-0p7cd-3000K',*bed_view),('bed-lamp-0p35cd-3500K',*bed_view),('bed-refinement-restored',*bed_view)]
 persist()
 try:result=review.run(views,capture_delay=15.,initial_delay=0.,before_view=before_view,on_finish=finish)
 except Exception:finish('Review launch refused');raise
 report['capture_receipt']=result['receipt'];persist();return {'comparison':str(path),'capture_receipt':result['receipt'],'temporary_existing_fixture_changes_only':True,'restored_prior_verified':False,'visual_acceptance':False}
