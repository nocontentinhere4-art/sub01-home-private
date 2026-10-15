"""Independent conservative furniture/capsule layout checks in UE centimetres.
No Unreal calls. Full house triangle sweep/native routing remain separate gates.
"""
import json,math,sys,hashlib
from pathlib import Path

def point_segment(p,a,b):
 d=[b[i]-a[i]for i in range(2)];length=sum(x*x for x in d);t=max(0,min(1,sum((p[i]-a[i])*d[i]for i in range(2))/length))if length else 0
 return math.dist(p,[a[i]+t*d[i]for i in range(2)])
def point_rect(p,r):return math.hypot(max(r[0]-p[0],0,p[0]-r[1]),max(r[2]-p[1],0,p[1]-r[3]))
def segment_rect(a,b,r):
 low,high=0.,1.
 for i,(lo,hi)in enumerate([(r[0],r[1]),(r[2],r[3])]):
  d=b[i]-a[i]
  if abs(d)<1e-12:
   if not lo<=a[i]<=hi:break
  else:
   u,v=(lo-a[i])/d,(hi-a[i])/d;u,v=sorted([u,v]);low=max(low,u);high=min(high,v)
   if low>high:break
 else:return 0.
 return min(point_rect(a,r),point_rect(b,r),*(point_segment(p,a,b)for p in [(r[0],r[2]),(r[0],r[3]),(r[1],r[2]),(r[1],r[3])]))
def prove(c):
 assert c['capsuleRadiusCm']==16 and c['capsuleHalfHeightCm']==91,'Require actual current R16/H91 source contract'
 assert c['tvFunctionalPlane']=={'x':-374.7,'y':[-88,78],'z':[117.5,212.5]},'Actual TV/input plane must remain exact'
 radius=c['capsuleRadiusCm'];margin=c['requiredSurfaceMarginCm'];obstacles=c['furniture'];sofa=obstacles['sofa'];table=obstacles['coffeeTable'];cabinet=obstacles['console'];gaps={'console_to_table_cm':table[0]-cabinet[1],'table_to_sofa_cm':sofa[0]-table[1],'sofa_back_to_stairs_cm':c['stairs'][0]-sofa[1]};required=2*(radius+margin)
 for n,g in gaps.items():assert g>=required,n+' insufficient: '+str(g)+' < '+str(required)
 routes=[]
 for route in c['proposedLocalRoutes']:
  checks=[]
  for a,b in zip(route['points'],route['points'][1:]):
   for name,r in {**obstacles,'stairs':c['stairs']}.items():
    distance=segment_rect(a,b,r);assert distance>=radius+margin-1e-9,route['name']+' swept capsule intersects '+name;checks.append({'from':a,'to':b,'obstacle':name,'centrelineMinimumDistanceCm':distance,'surfaceClearanceCm':distance-radius})
  routes.append({'name':route['name'],'checks':checks})
 screen=c['tvFunctionalPlane'];eye=c['proposedSeatedEyeCm'];distance=abs(eye[0]-screen['x']);angle=math.degrees(2*math.atan((screen['y'][1]-screen['y'][0])/(2*distance)));pitch=math.degrees(math.atan2(sum(screen['z'])/2-eye[2],distance));ray=[]
 for target_y in screen['y']:
  for target_z in screen['z']:
   # All rays stay above table/cabinet: exact linear segment interval minimum.
   for name in ['coffeeTable','console']:
    rect=obstacles[name];xlow,xhigh=max(min(eye[0],screen['x']),rect[0]),min(max(eye[0],screen['x']),rect[1])
    if xlow<=xhigh:
     points=[]
     for x in [xlow,xhigh]:
      u=(x-eye[0])/(screen['x']-eye[0]);points.append(eye[2]+u*(target_z-eye[2]))
     clearance=min(points)-c['maximumFurnitureHeightCm'][name];assert clearance>0,'Furniture blocks TV ray';ray.append({'obstacle':name,'TVCorner':[target_y,target_z],'verticalClearanceCm':clearance})
 opening=c['wallTVOpeningYZ'];case=c['actualTVCaseYZ'];clearances=[case[0]-opening[0],opening[1]-case[1],case[2]-opening[2],opening[3]-case[3]];assert min(clearances)>=2,'Feature wall touches retained TV case'
 assert c['nicheBackFrontXcm']<-384.25,'Niche back intersects retained TV rear'
 return {'schema':'sub01.independent-living-layout-proposal.v1','units':'UE cm','capsuleRadiusCm':radius,'capsuleHalfHeightCm':91,'requiredSurfaceMarginCm':margin,'gaps':gaps,'minimumPassageWidthCm':required,'localCapsuleRouteChecks':routes,'TVSightline':{'eyeToScreenPlaneCm':distance,'horizontalScreenAngleDegrees':angle,'pitchToScreenCentreDegrees':pitch,'cornerRayVerticalClearances':ray},'TVCaseOpeningMarginsCm':clearances,'TVRearToNicheBackCm':-384.25-c['nicheBackFrontXcm'],'tvPlaneAndInputBoundsUnchanged':True,'fullHouseGeometrySweepAccepted':False,'nativePlacementVerified':False,'otherNewAssetsAndDoorSweepsPending':True}
if __name__=='__main__':
 source,output=map(Path,sys.argv[1:]);c=json.loads(source.read_text());r=prove(c);r['configurationSha256']=hashlib.sha256(source.read_bytes()).hexdigest();output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'gaps':r['gaps'],'TVSightline':{k:v for k,v in r['TVSightline'].items()if k!='cornerRayVerticalClearances'}}))
