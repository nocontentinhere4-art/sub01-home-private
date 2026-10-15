"""Candidate-only read-only verification of exact owner-rejected source rug retirement."""
from pathlib import Path
import hashlib,json,time
RECEIPT=Path('/workspace/sub01-private-recovered-project/Sub01HomeLab/private-audit/rejected-generated-decor-hidden.json')
RECEIPT_SHA='a4b1416718bc1d2fff5564537d909e7c342720329f5e6f59f10ff2c0a5ac4b0f'
RUG='/Game/Sub01Home/ActualHome.ActualHome:PersistentLevel.full-home_node_61'
SOURCE='9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b'
def run():
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE
 from unreal_import_reference_entry import snapshot
 from unreal_import_reference_dressing import fingerprint
 assert active_candidate_guard();raw=RECEIPT.read_bytes();assert hashlib.sha256(raw).hexdigest()==RECEIPT_SHA;receipt=json.loads(raw);assert receipt['source_sha256']==SOURCE and RUG in receipt['removed_actor_paths'];eas=u.get_editor_subsystem(u.EditorActorSubsystem);actors=list(eas.get_all_level_actors());before=snapshot(u,actors);mapfile=CANDIDATE/'Content/Sub01Home/ActualHome.umap';mapsha=hashlib.sha256(mapfile.read_bytes()).hexdigest();matches=[a for a in actors if a.get_path_name()==RUG];assert len(matches)==1;actor=matches[0];assert actor.get_name()=='full-home_node_61'and actor.get_actor_label()=='house-static-8'and actor.get_editor_property('hidden')is True
 binding=fingerprint(u,[actor])[RUG];assert binding==receipt['old_state_before'][RUG],'Retired original rug binding/TRS/material/collision changed from exact durable receipt'
 assert all(c.get_collision_enabled()==u.CollisionEnabled.NO_COLLISION and str(c.get_collision_profile_name())=='NoCollision'for c in actor.get_components_by_class(u.StaticMeshComponent))
 assert snapshot(u,eas.get_all_level_actors())==before and hashlib.sha256(mapfile.read_bytes()).hexdigest()==mapsha and active_candidate_guard()
 result={'schema':'sub01.actual-retired-living-rug-readback.v1','originalSourceSha256':SOURCE,'retirementReceiptSha256':RECEIPT_SHA,'actor':RUG,'label':'house-static-8','actorHiddenInGame':True,'stateFingerprint':binding,'currentActorSnapshot':before[RUG],'worldSnapshotUnchanged':True,'mapUnchanged':True,'candidateMapSha256':mapsha,'candidateProject':str(CANDIDATE),'epoch':time.time(),'inputAcquired':False};(CANDIDATE/'private-audit/retired-living-rug-readback.json').write_text(json.dumps(result,indent=2)+'\n');return result
