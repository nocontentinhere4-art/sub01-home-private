"""Read-only exact saved native owner/Grip hard+soft package dependency closure."""
import json,hashlib,time
from pathlib import Path
def run():
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE
 from unreal_import_reference_entry import snapshot
 assert active_candidate_guard();eas=u.get_editor_subsystem(u.EditorActorSubsystem);before=snapshot(u,eas.get_all_level_actors());mapfile=CANDIDATE/'Content/Sub01Home/ActualHome.umap';sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();old=sha(mapfile)
 receipt=CANDIDATE/'private-audit/anatomical-grip-candidate.json';r=json.loads(receipt.read_text());assert r['assets_saved']and r['matching_existing_new_skeleton']and r['skeleton_file_unchanged']and r['keys']==152 and abs(r['duration_s']-151/30)<.0001
 ar=u.AssetRegistryHelpers.get_asset_registry();options=u.AssetRegistryDependencyOptions()
 options.set_editor_property('include_hard_package_references',True);options.set_editor_property('include_soft_package_references',True)
 todo=[r[k].split('.')[0]for k in ('clip','owner_mesh','skeleton')];seen=set();rows=[];external=[]
 while todo:
  package=todo.pop()
  if package in seen:continue
  seen.add(package)
  if not package.startswith('/Game/'):
   external.append(package);continue
  p=CANDIDATE/'Content'/Path(package.removeprefix('/Game/')).with_suffix('.uasset');assert p.is_file(),package
  rows.append({'package':package,'relative':str(p.relative_to(CANDIDATE)),'sha256':sha(p),'bytes':p.stat().st_size})
  todo.extend(map(str,ar.get_dependencies(package,options)))
 assert active_candidate_guard()and snapshot(u,eas.get_all_level_actors())==before and sha(mapfile)==old
 result={'schema':'sub01.native-wholeclip-asset-copy-manifest.v1','mesh':r['owner_mesh'],'skeleton':r['skeleton'],'clip':r['clip'],'source_sha256':r['source_sha256'],'keys':r['keys'],'duration_s':r['duration_s'],'grip_receipt_sha256':sha(receipt),'files':sorted(rows,key=lambda x:x['relative']),'external_packages':sorted(set(external)),'world_unchanged':True,'map_unchanged':True,'epoch':time.time()};p=CANDIDATE/'private-audit/wholeclip-asset-manifest.json';p.write_text(json.dumps(result,indent=2)+'\n');return {'report':str(p),'files':len(rows),'bytes':sum(x['bytes']for x in rows),'sha256':sha(p),'world_unchanged':True}
