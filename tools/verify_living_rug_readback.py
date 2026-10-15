"""Validate a precise read-only candidate retirement receipt; never infer absence."""
import hashlib,json,re
from pathlib import Path
RECEIPT_SHA='a4b1416718bc1d2fff5564537d909e7c342720329f5e6f59f10ff2c0a5ac4b0f'
SOURCE='9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b'
RUG='/Game/Sub01Home/ActualHome.ActualHome:PersistentLevel.full-home_node_61'
CANDIDATE='/workspace/sub01-private-candidate-20261015/Sub01HomeLab'
def verify(readback,original):
 assert hashlib.sha256(original).hexdigest()==RECEIPT_SHA;old=json.loads(original);r=json.loads(readback)
 assert old['source_sha256']==SOURCE and RUG in old['removed_actor_paths'];assert r['schema']=='sub01.actual-retired-living-rug-readback.v1'and r['originalSourceSha256']==SOURCE and r['retirementReceiptSha256']==RECEIPT_SHA
 assert r['actor']==RUG and r['label']=='house-static-8'and r['actorHiddenInGame']is True
 assert r['stateFingerprint']==old['old_state_before'][RUG]
 assert r['stateFingerprint']['components']and all(c['collision']=='<CollisionEnabled.NO_COLLISION: 0>'and c['profile']=='NoCollision'for c in r['stateFingerprint']['components'])
 assert r['currentActorSnapshot']['hidden']is True and r['worldSnapshotUnchanged']is True and r['mapUnchanged']is True and r['inputAcquired']is False
 assert r['candidateProject']==CANDIDATE and re.fullmatch('[0-9a-f]{64}',r['candidateMapSha256'])
 return {'readbackSha256':hashlib.sha256(readback).hexdigest(),'retirementReceiptSha256':RECEIPT_SHA,'retiredSourceNode':61,'actor':RUG,'actualHiddenAndNoCollision':True,'exactOriginalBindingAndTRSVerified':True,'candidateMapSha256':r['candidateMapSha256'],'candidateProject':CANDIDATE,'epoch':r['epoch']}
