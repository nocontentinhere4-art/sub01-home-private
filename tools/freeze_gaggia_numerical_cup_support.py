"""Complete one bounded clearance attempt using actual frozen contact XY geometry.

A pure vertical rigid offset preserves the actual contact projection and COM XY.
This proves numerical placement with <=0.25mm gaps, not dynamic touch/stability.
"""
import json,hashlib,math
from pathlib import Path
R=Path('/workspace/sub01-home-private/real-gaggia-gran-iraida-r1/placed-idle-r3');source=R/'gaggia-gran-idle-placed.glb';before_path=R/'independent-fit.json';clear_path=R/'cup-exact-vertical-clearance.json';before=json.loads(before_path.read_text());clear=json.loads(clear_path.read_text());sha=hashlib.sha256(source.read_bytes()).hexdigest();assert before['source_sha256']==clear['source_sha256']==sha
c=before['cup'];assert before['externalFullSourceIntersections']==[]and before['base']['passed']and c['closedCeramicMesh']and clear['beforeFullBVHIntersectionPairs']==312 and clear['afterWholeCupGrateFullBVHPairs']==0
lift=clear['minimumRigidCupLiftWith10MicrometreSeparationCm'];poly=c['contactHullXYcm'];com=c['uniformCeramicMassCOMcm'];assert len(poly)>=3 and c['contactPoints']>=3
margins=[]
for a,b in zip(poly,poly[1:]+poly[:1]):margins.append(((b[0]-a[0])*(com[1]-a[1])-(b[1]-a[1])*(com[0]-a[0]))/math.hypot(b[0]-a[0],b[1]-a[1]))
# The exact57measured supporting source projections were selected with actual
# nonnegative gap<=0.005cm. OnlyZ changes, so their convex hull and COM XY stay exact.
gap_upper=c['sourceContactBandCm']+lift;gap_lower=c['actualGrateGapCm']['min']+lift;accepted=min(margins)>0 and 0<=gap_lower<=gap_upper<=.025
r={'schema':'sub01.genuine-gaggia-numerical-cup-placement-proposal.v1','source_sha256_before_cup_raise':sha,'original_failed_fit_report_sha256':hashlib.sha256(before_path.read_bytes()).hexdigest(),'exact_clearance_report_sha256':hashlib.sha256(clear_path.read_bytes()).hexdigest(),'raw_before_cup_grate_pairs':312,'raw_before_fit_passed':before['passed'],'proposedCupOnlyRigidDeltaUEcm':[0,0,lift],'proposedCupOnlyRigidDeltaBlenderM':[0,0,lift/100],'afterFullCupGrateBVHPairs':0,'exactMeasuredSupportProjectionHullXYcm':poly,'actualMeasuredSupportProjectionPoints':c['contactPoints'],'originalUniformCeramicMassCOMcm':com,'afterMassCOMcm':[com[0],com[1],com[2]+lift],'minimumProjectionHullMarginCm':min(margins),'supportingSourceSkinGapBoundsAfterRaiseCm':[gap_lower,gap_upper],'rootReviewedMaximumNumericalGapCm':.025,'acceptedNumericalStaticPlacement':accepted,'actualTouchVerified':False,'dynamicStabilityVerified':False,'sourceGeometryMaterialChanges':False,'newDerivativeExportStillRequired':True,'nativeChanged':False};(R/'accepted-numerical-cup-placement.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r),flush=True);assert accepted
