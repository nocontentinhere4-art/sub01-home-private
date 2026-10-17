"""SERVER EDITOR: return the desk chair from its parked r15_chair_roll position to r15_chair_place.

Parked under the SALJAN desk, the seat approach falls inside the desk. This restores the exact
`before` translations recorded by r15_chair_roll_apply for the seven chair actors, only if each
actor still sits at that receipt's `after` translation (rotation and scale untouched). Writes
private-audit/chair-unpark.json; does not touch collision, materials or any other actor.
"""
import json
from pathlib import Path
import unreal as u

ROLL = Path('/workspace/sub01-private-candidate-20261015/Sub01HomeLab/private-audit/168-r15_chair_roll_apply-result.json')
LEVEL = '/Game/Sub01Home/ActualHome'

root = Path(u.Paths.project_dir()).resolve()
roll = json.loads(ROLL.read_text())['result']
if not u.get_editor_subsystem(u.LevelEditorSubsystem).load_level(LEVEL):
    raise RuntimeError('ActualHome unavailable')
actors = {a.get_path_name(): a for a in u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors()}
if set(roll['before']) != set(roll['after']) or len(roll['before']) != 7 or not set(roll['before']) <= set(actors):
    raise RuntimeError('Chair actors differ from the r15 roll receipt')
moved = []
for path, before in roll['before'].items():
    actor, parked = actors[path], roll['after'][path]['transform']['translation']
    here = actor.get_actor_location()
    if max(abs(here.x - parked[0]), abs(here.y - parked[1]), abs(here.z - parked[2])) > .05:
        raise RuntimeError(path + ' is not at the parked r15 position')
    target = before['transform']['translation']
    actor.set_actor_location(u.Vector(*target), False, False)
    moved.append({'actor': path, 'label': before.get('label'), 'from': parked, 'to': target})
if not u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level():
    raise RuntimeError('ActualHome save failed')
(root / 'private-audit/chair-unpark.json').write_text(json.dumps(
    {'schema': 'sub01.chair-unpark.v1', 'source_receipt': str(ROLL), 'moved': moved,
     'rotation_scale_unchanged': True, 'seat_contact_verified': False}, indent=2) + '\n')
u.log('SUB01_CHAIR_UNPARKED ' + str(len(moved)))
