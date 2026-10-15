import assert from 'node:assert/strict';
import * as T from '../web/house/vendor/three.core.js';
import {solveTwoBone,pelvisReachInterval,createFootPlantSolver} from './generated_owner_footplant_ik.mjs';
const V=(...a)=>new T.Vector3(...a);
for(const target of[V(.1,.1,.1),V(0,-.75,.04),V(.3,-.4,.2)]){
 const r=solveTwoBone(T,V(0,0,0),V(0,-.39,.1),V(0,-.8,0),target,.4,.41);
 assert(Math.abs(r.H.distanceTo(r.K)-.4)<1e-12);assert(Math.abs(r.A.distanceTo(r.K)-.41)<1e-12);assert(r.A.distanceTo(target)<1e-12);
}
assert.throws(()=>solveTwoBone(T,V(),V(0,-.4,0),V(0,-.8,0),V(2,0,0),.4,.4));
assert.throws(()=>pelvisReachInterval(V(),V(1,0,0),.4,.4));
const rig=new T.Group();rig.scale.setScalar(.01);
function bone(name,parent,p){let b=new T.Bone();b.name='mixamorig:'+name;b.position.fromArray(p);parent.add(b);return b;}
const hips=bone('Hips',rig,[0,90,0]);const c={schema:'sub01.actual-owner-sole-calibration.v1',owner_sha256:'7609eccbe81631c00d123e69c54241597e28861d1dc947999425cd6c3257adbb',feet:{}};
for(const [s,x]of[['Left',12],['Right',-12]]){let u=bone(s+'UpLeg',hips,[x,-5,0]),l=bone(s+'Leg',u,[0,-39,8]),f=bone(s+'Foot',l,[0,-39,-8]),toe=bone(s+'ToeBase',f,[0,-3,15]);c.feet[s]={patches:{heel:{bone:f.name,local_offset_cm:[0,-3,-3]},toe_inner:{bone:toe.name,local_offset_cm:[-3,0,0]},toe_outer:{bone:toe.name,local_offset_cm:[3,0,0]}}};}
rig.updateMatrixWorld(true);const initial=new Map();rig.traverse(b=>{if(b.isBone)initial.set(b,{p:b.position.clone(),q:b.quaternion.clone()});});
const restore=()=>{for(const[b,v]of initial){b.position.copy(v.p);b.quaternion.copy(v.q);}rig.updateMatrixWorld(true);};
const solver=createFootPlantSolver(T,rig,c);let r=solver.apply({frame:0,contacts:[true,true,true,true,true,true]});assert(!r.world_horizontal_lock_applied);
for(const s of['Left','Right'])for(const p of Object.values(c.feet[s].patches)){const b=rig.getObjectByName(p.bone),point=V(...p.local_offset_cm).applyMatrix4(b.matrixWorld);assert(Math.abs(point.y)<2e-5,`sole y ${point.y}`);}
restore();assert.throws(()=>solver.apply({frame:1,contacts:[true,true,true,true,true,true],groundPlanes:{Left:{point:[0,0,0],normal:[0,0,1]}}}));
// Failed frame must not consume time or strand anchor state.
restore();r=solver.apply({frame:1,contacts:[true,true,true,true,true,true],placement:new T.Matrix4(),physicalPlacementVerified:true,referencePlanarSpeedMps:1,actualPlanarSpeedMps:0});assert(!r.world_horizontal_lock_applied);
restore();r=solver.apply({frame:2,contacts:[true,true,true,true,true,true],placement:new T.Matrix4(),physicalPlacementVerified:true,referencePlanarSpeedMps:0,actualPlanarSpeedMps:0});assert(r.world_horizontal_lock_applied);
for(const[b,v]of initial)if(b!==hips)assert(b.position.distanceTo(v.p)<1e-12);
assert.equal(hips.position.x,0);assert.equal(hips.position.z,0);
console.log('PASS fixed-length analytic reach, actual FK sole projection, immutable translations, speed gate, failed-frame retry');
