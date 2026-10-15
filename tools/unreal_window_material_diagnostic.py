"""Read only the first owned refused window mesh's actual material slots."""
from pathlib import Path
import json

def run():
 import unreal as u
 p=Path(u.Paths.project_dir());a=p/'private-audit';r=json.loads((a/'real-home-windows-native-refusal.json').read_text());dest=r['quarantined_assets']
 if not dest.startswith('/Game/Sub01Home/ResidentialWindows/V_7119c36483ec/Attempt_'):raise RuntimeError('Exact owned frozen window namespace required')
 rows=[]
 for path in u.EditorAssetLibrary.list_assets(dest,recursive=True,include_folder=False):
  o=u.load_asset(path)
  if not isinstance(o,u.StaticMesh):continue
  slots=o.get_editor_property('static_materials');rows.append({'path':path,'slots':[{'slot':str(s.get_editor_property('material_slot_name')),'imported_slot':str(s.get_editor_property('imported_material_slot_name')),'material':s.get_editor_property('material_interface').get_path_name()if s.get_editor_property('material_interface')else None}for s in slots]})

 unique=sorted({(x['slot'],x['imported_slot'],x['material'])for row in rows for x in row['slots']})
 result={'unique_slots':unique,'schema':'sub01.actual-window-material-slots.v1','namespace':dest,'scene_mutations':False,'meshes':rows};(a/'residential-window-material-slots.json').write_text(json.dumps(result,indent=2)+'\n');return result
