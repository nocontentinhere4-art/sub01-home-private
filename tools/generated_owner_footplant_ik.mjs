// Source-only contact IK. Never writes CharacterMovement, capsule, mesh scale,
// bone lengths, or non-Hips translations. Native/contact acceptance is external.
import assert from 'node:assert/strict';
const clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
export function solveTwoBone(THREE,H,K,A,T,L1,L2,pole){
 const axis=T.clone().sub(H),d=axis.length();
 assert(d>1e-8&&d<L1+L2+1e-6&&d>Math.abs(L1-L2)-1e-6,'Target outside fixed-length two-bone reach');axis.multiplyScalar(1/d);
 let bend=K.clone().sub(H);bend.addScaledVector(axis,-bend.dot(axis));
 if(bend.lengthSq()<1e-12){bend=(pole||new THREE.Vector3(0,0,1)).clone();bend.addScaledVector(axis,-bend.dot(axis));}
 assert(bend.lengthSq()>1e-12,'Measured knee pole required at singular alignment');bend.normalize();
 const along=(L1*L1+d*d-L2*L2)/(2*d),height=Math.sqrt(Math.max(0,L1*L1-along*along));
 return{H:H.clone(),K:H.clone().addScaledVector(axis,along).addScaledVector(bend,height),A:T.clone()};
}
export function pelvisReachInterval(H,T,L1,L2,maxOffset=.12){
 const max=L1+L2-1e-6,horizontal2=(T.x-H.x)**2+(T.z-H.z)**2;
 assert(horizontal2<max*max,'Foot target unreachable by pelvis-Y adjustment');
 const vertical=Math.sqrt(max*max-horizontal2),center=T.y-H.y;
 return[Math.max(-maxOffset,center-vertical),Math.min(maxOffset,center+vertical)];
}
export function createFootPlantSolver(THREE,rig,calibration,options={}){
 assert(calibration.schema==='sub01.actual-owner-sole-calibration.v1');
 assert(calibration.owner_sha256==='7609eccbe81631c00d123e69c54241597e28861d1dc947999425cd6c3257adbb');
 const V=a=>new THREE.Vector3().fromArray(a),Q=()=>new THREE.Quaternion(),M=()=>new THREE.Matrix4();
 const bones=new Map();rig.traverse(o=>{if(o.isBone)bones.set(o.name,o);});
 const hips=bones.get('mixamorig:Hips');assert(hips,'Actual owner hips required');rig.updateMatrixWorld(true);
 const originalPositions=new Map([...bones.values()].map(b=>[b,b.position.clone()]));
 const state={pelvis:0,feet:{Left:{},Right:{}},lastFrame:null};
 const feet={};
 const pos=b=>b.getWorldPosition(new THREE.Vector3());
 for(const side of['Left','Right']){
  const upper=bones.get(`mixamorig:${side}UpLeg`),lower=bones.get(`mixamorig:${side}Leg`),foot=bones.get(`mixamorig:${side}Foot`);assert(upper&&lower&&foot);
  const L1=pos(upper).distanceTo(pos(lower)),L2=pos(lower).distanceTo(pos(foot));assert(L1>.25&&L1<.55&&L2>.25&&L2<.55);
  feet[side]={upper,lower,foot,L1,L2,patches:calibration.feet[side].patches};
 }
 function patchPoint(part){const b=bones.get(part.bone);assert(b);return V(part.local_offset_cm).applyMatrix4(b.matrixWorld);}
 function patchPoints(side){const p=feet[side].patches;return['heel','toe_inner','toe_outer'].map(k=>patchPoint(p[k]));}
 function setWorldQ(b,q){const parent=b.parent.getWorldQuaternion(Q());b.quaternion.copy(parent.invert().multiply(q)).normalize();rig.updateMatrixWorld(true);}
 function applyLeg(side,target,orientation){
  const f=feet[side],H=pos(f.upper),K=pos(f.lower),A=pos(f.foot);const solved=solveTwoBone(THREE,H,K,A,target,f.L1,f.L2);
  const dq=Q().setFromUnitVectors(K.clone().sub(H).normalize(),solved.K.clone().sub(H).normalize());setWorldQ(f.upper,dq.multiply(f.upper.getWorldQuaternion(Q())));
  const actualK=pos(f.lower),actualA=pos(f.foot);const lowerDelta=Q().setFromUnitVectors(actualA.clone().sub(actualK).normalize(),target.clone().sub(actualK).normalize());setWorldQ(f.lower,lowerDelta.multiply(f.lower.getWorldQuaternion(Q())));setWorldQ(f.foot,orientation);
  assert(pos(f.foot).distanceTo(target)<2e-5,'Actual ankle FK did not reach solved target');
 }
 return{apply({frame,contacts,dt=1/30,grounded=true,placement=null,physicalPlacementVerified=false,referencePlanarSpeedMps=null,actualPlanarSpeedMps=null,groundPlanes=null,pelvisVerticalOffsetM=null}){
  assert(Number.isInteger(frame)&&Array.isArray(contacts)&&contacts.length===6&&dt>0&&dt<=.1);
  assert(state.lastFrame===null||frame===state.lastFrame+1,'Contact IK must run sequentially; reset state for a new take');
  const savedState={pelvis:state.pelvis,lastFrame:state.lastFrame,feet:Object.fromEntries(Object.entries(state.feet).map(([k,v])=>[k,{...v,anchor:v.anchor?.clone()}]))};
  const captured=new Map([...bones.values()].map(b=>[b,{p:b.position.clone(),q:b.quaternion.clone()}]));
  const hipsXZ=[hips.position.x,hips.position.z],hipsY=hips.position.y,place=placement?placement.clone():M(),inverse=place.clone().invert();
  const pScale=new THREE.Vector3(),pRot=Q(),pTrans=new THREE.Vector3();place.decompose(pTrans,pRot,pScale);assert(pScale.distanceTo(new THREE.Vector3(1,1,1))<1e-8,'Physical placement must be rigid metres, never a body scale');
  const actualSpeed=actualPlanarSpeedMps,referenceSpeed=referencePlanarSpeedMps;
  const speedCompatible=Number.isFinite(actualSpeed)&&Number.isFinite(referenceSpeed)&&Math.abs(actualSpeed-referenceSpeed)<=Math.max(.10,Math.abs(referenceSpeed)*.25);
  const worldLock=grounded&&physicalPlacementVerified&&!!placement&&speedCompatible;
  const report={frame,grounded,world_horizontal_lock_applied:worldLock,speed_compatible:speedCompatible,physical_placement_verified:physicalPlacementVerified,source_stance_channels:contacts,feet:{},capsule_changed:false,non_hips_translations_changed:false,native_contact_accepted:false};
  try{
   rig.updateMatrixWorld(true);const up=new THREE.Vector3(0,1,0);const parentQ=hips.parent.getWorldQuaternion(Q());assert(up.clone().applyQuaternion(parentQ).dot(up)>.999999,'Owner parent requires explicit Y-up gravity adapter');
   const plans={};let interval=[-(options.maxPelvisOffsetM??.12),options.maxPelvisOffsetM??.12];
   for(const[side,offset]of[['Left',0],['Right',3]]){
    const flags=contacts.slice(offset,offset+3),heel=!!flags[0],toe=!!(flags[1]||flags[2]);const f=feet[side],old=state.feet[side];
    if(!grounded||(!heel&&!toe)){state.feet[side]={};continue;}
    const plane=groundPlanes?.[side]||{point:[0,0,0],normal:[0,1,0]};const normalWorld=V(plane.normal).normalize();assert(normalWorld.dot(up)>.7071,'Ground slope outside declared45-degree solver range');
    const normalModel=normalWorld.clone().applyQuaternion(pRot.clone().invert()).normalize(),planePoint=V(plane.point),points=patchPoints(side),ankle=pos(f.foot),originalQ=f.foot.getWorldQuaternion(Q());let goalQ=originalQ.clone(),rot=Q();
    if(heel&&toe){
     const n=points[1].clone().sub(points[0]).cross(points[2].clone().sub(points[0])).normalize();if(n.dot(up)<0)n.negate();
     const angle=Math.acos(clamp(n.dot(normalModel),-1,1));assert(angle<(options.maxSoleTiltDegrees??35)*Math.PI/180,'Source stance sole tilt exceeds bounded physical correction');rot.setFromUnitVectors(n,normalModel);goalQ.premultiply(rot);
    }
    const chosen=heel&&toe?points:heel?[points[0]]:[points[1],points[2]],center=chosen.reduce((v,p)=>v.add(p),new THREE.Vector3()).multiplyScalar(1/chosen.length);
    const projectedWorld=center.clone().applyMatrix4(place);projectedWorld.addScaledVector(normalWorld,-projectedWorld.clone().sub(planePoint).dot(normalWorld));
    const phase=`${heel?1:0}${toe?1:0}`;let anchor=projectedWorld;
    if(worldLock){if(old.phase===phase&&old.anchor)anchor=old.anchor.clone();state.feet[side]={phase,anchor:anchor.clone()};}else state.feet[side]={};
    const goalCenter=anchor.clone().applyMatrix4(inverse),rotatedOffset=center.clone().sub(ankle).applyQuaternion(rot),target=goalCenter.sub(rotatedOffset);
    const reach=pelvisReachInterval(pos(f.upper),target,f.L1,f.L2,options.maxPelvisOffsetM??.12);interval=[Math.max(interval[0],reach[0]),Math.min(interval[1],reach[1])];const H=pos(f.upper),capturedLength=H.distanceTo(ankle),horizontal2=(target.x-H.x)**2+(target.z-H.z)**2;
    const preferredPelvisY=horizontal2<capturedLength**2?target.y-H.y+Math.sqrt(capturedLength**2-horizontal2):null;
    plans[side]={target,orientation:goalQ,phase,plane,ground:normalModel,preferredPelvisY};
   }
   assert(interval[0]<=interval[1],'Both stance constraints exceed bounded pelvis-Y reach');
   if(pelvisVerticalOffsetM!==null)assert(Number.isFinite(pelvisVerticalOffsetM)&&pelvisVerticalOffsetM>=interval[0]-1e-9&&pelvisVerticalOffsetM<=interval[1]+1e-9,'Planned pelvis correction must remain within measured stance reach');
   const preferred=Object.values(plans).map(p=>p.preferredPelvisY).filter(Number.isFinite),eased=state.pelvis*Math.exp(-8*dt),desired=preferred.length?preferred.reduce((a,b)=>a+b,0)/preferred.length:eased,delta=clamp(pelvisVerticalOffsetM??desired,interval[0],interval[1]);const rootWorld=pos(hips).add(new THREE.Vector3(0,delta,0));const local=hips.parent.worldToLocal(rootWorld);
   assert(Math.abs(local.x-hipsXZ[0])<1e-5&&Math.abs(local.z-hipsXZ[1])<1e-5,'Pelvis-Y correction changed physical root XZ');hips.position.y=local.y;rig.updateMatrixWorld(true);
   report.pelvis_feasible_interval_m=interval;report.pelvis_preferred_offset_m=preferred.length?preferred.reduce((a,b)=>a+b,0)/preferred.length:null;report.pelvis_vertical_body_offset_m=delta;report.source_hips_local_y=hipsY;
   for(const side of['Left','Right']){
    const f=feet[side],plan=plans[side];
    if(plan){applyLeg(side,plan.target,plan.orientation);report.feet[side]={mode:'measured-sole-stance-IK',phase:plan.phase,ankle_target_world_model_m:plan.target.toArray()};}
    else if(grounded){
     const plane=groundPlanes?.[side]||{point:[0,0,0],normal:[0,1,0]},normalWorld=V(plane.normal).normalize(),point=V(plane.point),patches=patchPoints(side);const clearance=Math.min(...patches.map(p=>p.clone().applyMatrix4(place).sub(point).dot(normalWorld)));
     if(clearance<(options.swingClearanceM??.003)){const correction=normalWorld.multiplyScalar((options.swingClearanceM??.003)-clearance).applyQuaternion(pRot.clone().invert());applyLeg(side,pos(f.foot).add(correction),f.foot.getWorldQuaternion(Q()));report.feet[side]={mode:'swing-ground-clearance-IK',measured_patch_clearance_before_m:clearance};}else report.feet[side]={mode:'captured-swing-preserved'};
    }
   }
   // Optional exact skinned sole support, not an arbitrary global root shift.
   // Callback operates in model-world Y-up metres against this same fixed skin.
   if(options.measureSoleSurface&&grounded){
    assert(!placement&&!groundPlanes,'Exact skin support adapter requires declared level model-world floor');
    for(const side of['Left','Right']){
     let correction=0;const targetClearance=plans[side]?0:(options.swingClearanceM??.003);
     for(let iteration=0;iteration<4;iteration++){
      const measured=options.measureSoleSurface(side);assert(Number.isFinite(measured));
      const error=targetClearance-measured;if(Math.abs(error)<1e-5||(error<0&&!plans[side]))break;
      assert(Math.abs(error)<.025,`Exact sole correction exceeds bounded25mm contact refinement: ${side} frame=${frame} measured=${measured}m error=${error}m`);
      const f=feet[side];applyLeg(side,pos(f.foot).add(new THREE.Vector3(0,error,0)),f.foot.getWorldQuaternion(Q()));correction+=error;
     }
     report.feet[side]={...report.feet[side],actual_skinned_sole_min_y_m:options.measureSoleSurface(side),measured_surface_refinement_m:correction};
    }
   }
   for(const[b,p]of originalPositions)if(b!==hips)assert(Math.min(b.position.distanceTo(p),b.position.distanceTo(new THREE.Vector3(Math.fround(p.x),Math.fround(p.y),Math.fround(p.z))))<1e-8,'Fixed original non-Hips translation was changed beyond exact float32 serialization');
   assert(hips.position.x===hipsXZ[0]&&hips.position.z===hipsXZ[1]);state.pelvis=delta;state.lastFrame=frame;return report;
  }catch(error){Object.assign(state,savedState);for(const[b,pose]of captured){b.position.copy(pose.p);b.quaternion.copy(pose.q);}rig.updateMatrixWorld(true);throw error;}
 }};
}
