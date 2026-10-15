"""Save the actually reviewed finite emitter in the existing real bedside lamp."""
import copy,hashlib,json,shutil,time,struct
from pathlib import Path

def configured_power(text):
 section='[/Script/Sub01HomeLab.Sub01HomeCharacter]';lines=text.splitlines(keepends=True);starts=[i for i,l in enumerate(lines)if l.strip()==section]
 if not starts or any(l.strip().startswith('BedsideLampIntensityCandela=')for l in lines):raise RuntimeError('Existing character configuration with no prior custom power required')
 # UE merges repeated class sections. Append only our one new key, preserving
 # every existing camera/contact/profile setting byte for byte.
 return text+(''if text.endswith('\n')else'\n')+'\n'+section+'\nBedsideLampIntensityCandela=0.35\n'

def run():
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE
 from unreal_import_reference_entry import snapshot
 assert active_candidate_guard(u.Paths.project_dir());proof=json.loads((CANDIDATE/'private-audit/bed-lamp-fullsource.json').read_text());glass=[r for r in proof['sections']if r['source_material'].endswith('_glass.SUB01_RealLamp_BedLamp_industrial_pipe_lamp_glass')];assert len(glass)==1 and proof['original_untouched'];center=glass[0]['bbox_center_cm'];radius=glass[0]['half_shortest_glass_extent_cm']*.5
 eas=u.get_editor_subsystem(u.EditorActorSubsystem);actors=list(eas.get_all_level_actors());before=snapshot(u,actors);found=[a for a in actors if a.get_actor_label()=='SUB01_AuthoredLight_BedLamp'];assert len(found)==1;actor=found[0];cs=actor.get_components_by_class(u.PointLightComponent);assert len(cs)==1;light=cs[0];oldpos=actor.get_actor_location();keys=['intensity','temperature','use_temperature','source_radius'];old={k:light.get_editor_property(k)for k in keys}
 if old!={'intensity':0.,'temperature':2700.,'use_temperature':True,'source_radius':0.}:raise RuntimeError('Exact original lamp baseline required')
 ini=CANDIDATE/'Config/DefaultGame.ini';old_ini=ini.read_bytes();new_ini=configured_power(old_ini.decode()).encode();map_path=CANDIDATE/'Content/Sub01Home/ActualHome.umap';backup=CANDIDATE/'Saved/PrivateMapBackups'/('chosen-bedlamp-'+str(time.time_ns()));backup.mkdir(parents=True);shutil.copy2(map_path,backup/'ActualHome.umap');shutil.copy2(ini,backup/'DefaultGame.ini');expected=copy.deepcopy(before);expected[actor.get_path_name()]['transform']['translation']=center;attempted=False
 try:
  actor.set_actor_location(u.Vector(*center),False,True);light.set_editor_property('source_radius',radius);light.set_editor_property('temperature',3500.);light.set_editor_property('use_temperature',True);light.set_intensity(.35)
  if snapshot(u,list(eas.get_all_level_actors()))!=expected or {k:light.get_editor_property(k)for k in keys}!={'intensity':struct.unpack('<f',struct.pack('<f',.35))[0],'temperature':3500.,'use_temperature':True,'source_radius':struct.unpack('<f',struct.pack('<f',radius))[0]}:raise RuntimeError('Only the exact existing physical emitter chosen values and position may change')
  ini.write_bytes(new_ini);assert active_candidate_guard(u.Paths.project_dir());attempted=True
  if not u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level():raise RuntimeError('Chosen real bedside lamp map save refused')
  result={'schema':'sub01.actual-candidate-chosen-bedside-lamp.v1','saved':True,'actual_bulb_center_cm':center,'finite_emitter_radius_cm':radius,'chosen_candela':.35,'chosen_kelvin':3500,'existing_real_fixture_only':True,'new_lights':0,'all_other_actor_geometry_transforms_materials_collisions_exact':True,'default_config_power':.35,'runtime_configurable_power_patch_required_before_ON_OFF_acceptance':True,'map_sha256':hashlib.sha256(map_path.read_bytes()).hexdigest(),'config_sha256':hashlib.sha256(new_ini).hexdigest(),'backup':str(backup),'live_game_or_input_changed':False,'runtime_switch_accepted':False};(CANDIDATE/'private-audit/chosen-bed-lamp-native.json').write_text(json.dumps(result,indent=2)+'\n');return result
 except Exception:
  actor.set_actor_location(oldpos,False,True)
  for k,v in old.items():light.set_editor_property(k,v)
  ini.write_bytes(old_ini)
  if snapshot(u,list(eas.get_all_level_actors()))!=before:raise RuntimeError('Exact original complete world rollback required')
  if attempted and not u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level():raise RuntimeError('Chosen bedside rollback save refused')
  raise
