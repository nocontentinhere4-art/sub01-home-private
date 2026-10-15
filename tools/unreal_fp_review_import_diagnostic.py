"""Read-only inspection of the exact refused owned keyboard review import."""
import json
from pathlib import Path

def run():
 import unreal as u
 project=Path(u.Paths.project_dir());f=project/'private-audit/fp-keyboard-review-import-refusal.json';r=json.loads(f.read_text());dest=r['owned_assets_quarantined']
 if not dest.startswith('/Game/Sub01Hands/KeyboardReview/V_07baf00adbe6_')or not r['world_and_config_untouched']:raise RuntimeError('Exact refused private review namespace required')
 rows=[]
 for path in u.EditorAssetLibrary.list_assets(dest,recursive=True,include_folder=False):
  o=u.load_asset(path);row={'path':path,'class':o.get_class().get_name()if o else None}
  if isinstance(o,u.AnimSequence):row.update(keys=int(u.AnimationLibrary.get_num_keys(o)),duration=float(o.get_editor_property('sequence_length')),skeleton=o.get_editor_property('skeleton').get_path_name())
  if isinstance(o,u.SkeletalMesh):row.update(skeleton=o.get_editor_property('skeleton').get_path_name(),slots=[str(m.get_editor_property('material_slot_name'))for m in o.get_editor_property('materials')])
  rows.append(row)
 result={'schema':'sub01.fp-review-refused-asset-inspection.v1','exact_owned_namespace':dest,'assets':rows,'scene_mutations':False};(project/'private-audit/fp-keyboard-refused-assets.json').write_text(json.dumps(result,indent=2)+'\n');return result
