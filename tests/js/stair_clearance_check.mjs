import {staticBodyAllows,showerSupportHeight} from '../../web/house/static_clearance.mjs';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {execFileSync} from 'node:child_process';
import {STAIR_CLEARANCE as A, stairClearanceAllows as allows} from '../../web/house/stair_clearance.mjs';
import * as T from '../../web/house/vendor/three.module.js';
import {balconyAllows} from '../../web/house/balcony_access.mjs';
import {frontDoorAllows} from '../../web/house/front_door_access.mjs';
import {bathroomAllows} from '../../web/house/bathroom_access.mjs';
import {createLowerKitchenCabinet} from '../../web/house/lower_kitchen_cabinet.mjs';
import {RoundedBoxGeometry} from '../../web/house/vendor/RoundedBoxGeometry.js';
import {mergeGeometries} from '../../web/house/vendor/BufferGeometryUtils.js';
import {streetAccessAllows} from '../../web/house/street_access.mjs';

// Run the actual staircase builder with a geometry recorder. This catches
// changed mesh dimensions, not just a helper agreeing with its own constants.
const source = fs.readFileSync(new URL('../../web/house/home.js',import.meta.url),'utf8');
const begin = source.indexOf('for (let i = 0; i < 17; i++) {',source.indexOf('const STEP ='));
const end = source.indexOf('for (const x of [-0.25, 0.85])',begin);
assert.ok(begin > 0 && end > begin);
const boxes = [];
new Function('box','M',source.slice(begin,end))((w,h,d,x,y,z)=>boxes.push({w,h,d,x,y,z}),{wall:{},architectureOak:{}});
assert.equal(boxes.length, A.count * 2);
// Execute the actual raised floor support-box expression and actual floor calls.
// This keeps the added headroom bounds tied to real loft/landing/balcony geometry.
const supportLine=source.split('\n').find(line=>line.trim().startsWith('box(w, 0.12, d,'));
assert.ok(supportLine);
const slabs=[];
const buildSlab=new Function('w','d','x','y','z','M','box',supportLine);
for(const call of source.matchAll(/^floor\(([\d., \-]+)\);/gm)){
 const args=call[1].split(',').map(Number);if(args[3]<=0)continue;
 buildSlab(...args,{wall:{},architectureOak:{}},(w,h,d,x,y,z)=>slabs.push({x0:x-w/2,x1:x+w/2,z0:z-d/2,z1:z+d/2,low:y-h/2,high:y+h/2}));
}
assert.equal(slabs.length,A.loftSlabs.length);
for(let i=0;i<slabs.length;i++)for(const key of Object.keys(slabs[i]))assert.ok(Math.abs(slabs[i][key]-A.loftSlabs[i][key])<1e-12,`Actual raised floor mismatch: ${i}.${key}`);
for (let i=0;i<A.count;i++) {
  const body=boxes[i*2],tread=boxes[i*2+1];
  assert.equal(body.w,A.bodyWidth); assert.equal(body.d,A.run);
  assert.equal(body.x,A.centre); assert.equal(body.h,(i+1)*A.rise/A.count);
  assert.equal(body.z,A.bottom-(i+.5)*A.run);
  assert.equal(tread.w,A.treadWidth); assert.equal(tread.d,A.treadDepth);
  assert.equal(tread.h,A.treadThickness); assert.equal(tread.y,body.h+A.treadOffset);
}

// Raycast the actual generated boxes: the formerly reachable eye is only
// .03 m from the side, inside the .04 m camera near plane.
const eye=[.81,1.65,-.5];
const hits=boxes.filter(b=>eye[1]>=b.y-b.h/2 && eye[1]<=b.y+b.h/2 &&
  eye[2]>=b.z-b.d/2 && eye[2]<=b.z+b.d/2 && eye[0]>=b.x+b.w/2)
  .map(b=>eye[0]-(b.x+b.w/2));
assert.ok(Math.min(...hits)<.04);
assert.equal(allows(eye[0],eye[2],0),false);
assert.equal(allows(.93,-.5,0),false);
assert.equal(allows(.96,-.5,0),true);
// A low tread projects further than a high tread above the standing head.
assert.equal(allows(.95,2.1,0),false);
assert.equal(allows(.98,2.1,0),false,'Tread clearance alone does not clear real post/handrail');
assert.equal(allows(1.05,2.1,0),true);
assert.equal(allows(.81,-.5,3),false,'Raised rail remains solid above an upper-floor walker');
assert.equal(allows(-.5,-.5,3),true,'Clear loft-side movement stays available');
for (const x of [.3,1.3,2,-.45]) assert.equal(allows(x,3.2,0),true,'Ground approach around base');
for (let i=0;i<=170;i++) {
  const z=A.bottom-(A.bottom-A.top)*i/170, feet=A.rise*i/170;
  assert.equal(allows(.3,z,feet),true,'Entire real centre stair route');
  assert.equal(allows(.79,z,feet),false,'Body cannot hang through tread edge');
}
assert.equal(allows(.3,-2.1,3),true,'Upper landing stays accessible');

// Build the actual sloping oak rails/brass posts from home.js; these extend
// beyond tread/body bounds and were previously absent from the collider.
const railStart=source.indexOf('for (const x of [-0.25, 0.85])',end);
const railEnd=source.indexOf('// Safe landing',railStart);
const railScene=new T.Scene(),rails=[];
new Function('beam','M',source.slice(railStart,railEnd))((p,q,r)=>{
  rails.push({p,q,r});const delta=new T.Vector3(...q).sub(new T.Vector3(...p));
  const mesh=new T.Mesh(new T.CylinderGeometry(r,r,delta.length(),10),new T.MeshStandardMaterial());
  mesh.position.copy(new T.Vector3(...p).add(new T.Vector3(...q)).multiplyScalar(.5));
  mesh.quaternion.setFromUnitVectors(new T.Vector3(0,1,0),delta.normalize());railScene.add(mesh);
},{architectureOak:{},brass:{}});
assert.equal(rails.length,2*(A.postCount+1));
assert.equal(rails.filter(r=>r.r===A.railRadius).length,2);
assert.equal(rails.filter(r=>r.r===A.postRadius).length,18);
for(let side=0;side<2;side++){
  const offset=side*(A.postCount+1),x=A.railXs[side];
  assert.deepEqual(rails[offset].p,[x,A.railHeight,A.bottom]);
  assert.deepEqual(rails[offset].q,[x,A.rise+A.railHeight,A.top]);
  for(let i=0;i<A.postCount;i++){
    const z=A.bottom-i*A.postSpacing,h=A.rise*(A.bottom-z)/(A.bottom-A.top);
    assert.deepEqual(rails[offset+i+1].p,[x,h,z]);
    assert.deepEqual(rails[offset+i+1].q,[x,h+A.railHeight,z]);
  }
}
railScene.updateMatrixWorld(true);
// The real sloping oak rail is above the eye but inside a standing head.
// Actual generated cylinder triangles enter the .16m head sphere centred at
// feet+1.66 (the new capsule cap); the old
// eye-as-body-top capsule falsely admitted the location.
const headRadius=.16,headCentre=new T.Vector3(1,1.82-headRadius,1.3);
const railLine=new T.Line3(new T.Vector3(.85,.9,2.55),new T.Vector3(.85,3.9,-1.7));
const nearest=railLine.closestPointToPoint(headCentre,true,new T.Vector3());
const headRay=new T.Raycaster(headCentre,nearest.sub(headCentre).normalize(),0,headRadius);
const headHits=headRay.intersectObjects(railScene.children);
assert.ok(headHits.length,'Actual oak rail triangles intersect standing head sphere');
assert.ok(headHits[0].point.y>1.65,'Physical intersection is above eye height');
const helperSource=fs.readFileSync(new URL('../../web/house/stair_clearance.mjs',import.meta.url),'utf8');
const oldEyeHeightHelper=await import('data:text/javascript,'+encodeURIComponent(helperSource.replace('bodyHeight: 1.82','bodyHeight: 1.65')));
assert.equal(oldEyeHeightHelper.stairClearanceAllows(1,1.3,0),true,'Former eye-as-top missed this real above-eye rail contact');
assert.equal(allows(1,1.3,0),false,'Standing head now clears physical sloping rail');
assert.equal(allows(1.045,1.3,0),true,'Clear aisle beyond rail/head remains available');
assert.equal(A.bodyHeight,1.82);
console.log('Above-eye head contact:',JSON.stringify({position:[1,0,1.3],triangleHit:headHits[0].point.toArray(),distanceFromHeadCentre:headHits[0].distance,headRadius,oldAllowed:true,newAllowed:false}));
const loftSlab=slabs[0];
const loftMesh=new T.Mesh(new T.BoxGeometry(loftSlab.x1-loftSlab.x0,loftSlab.high-loftSlab.low,loftSlab.z1-loftSlab.z0),new T.MeshStandardMaterial());
loftMesh.position.set((loftSlab.x0+loftSlab.x1)/2,(loftSlab.low+loftSlab.high)/2,(loftSlab.z0+loftSlab.z1)/2);loftMesh.updateMatrixWorld(true);
const loftHead=new T.Vector3(-.05,1.2+1.82-headRadius,.85);
const loftRay=new T.Raycaster(loftHead,new T.Vector3(-.201,2.881,.85).sub(loftHead).normalize(),0,headRadius);
const loftHits=loftRay.intersectObject(loftMesh);
assert.ok(loftHits.length,'Actual floor support-box triangles enter rounded head beside ramp');
assert.ok(loftHits[0].point.y>1.2+1.65,'Loft contact lies above the still-clear eye');
assert.equal(oldEyeHeightHelper.stairClearanceAllows(-.05,.85,1.2),true,'Former eye-height body misses real loft corner');
assert.equal(allows(-.05,.85,1.2),false,'Only the real rounded head/loft-edge intersection is rejected');
assert.equal(allows(-.035,.85,1.2),true,'Moving15mm toward stair centre clears the actual loft edge');
assert.equal(allows(-1,.85,0),true,'Ground walker safely below loft stays available');
assert.equal(allows(-1,.85,3),true,'Upper-floor support is not a head obstruction');
console.log('Loft rounded-head contact:',JSON.stringify({position:[-.05,1.2,.85],triangleHit:loftHits[0].point.toArray(),distanceFromHeadCentre:loftHits[0].distance,headRadius}));
const railRay=new T.Raycaster(new T.Vector3(1,1.60,.55),new T.Vector3(-1,0,0),0,.16);
assert.ok(railRay.intersectObjects(railScene.children).length,'Actual post triangles intersect formerly allowed body');
assert.equal(allows(1,.55,0),false,'Ground aisle cannot clip raised stair post');
assert.equal(allows(1.03,.55,0),true,'Only real post clearance is added');
assert.equal(allows(-.3,-1.7,3),false,'Upper-floor body cannot clip sloping rail endpoint');
assert.equal(allows(-.5,-1.7,3),true,'Loft-side passage remains available');
assert.equal(allows(1,.55,3),true,'Rail below upper-floor feet does not block');

// Exercise the real visitor collision function with the proposed hook before
// integration, or directly once home.js has the hook. Geometry is untouched.
const walkStart=source.indexOf('function floorAt(');
const walkEnd=source.indexOf('document.getElementById("follow").onclick',walkStart);
let walkSource=source.slice(walkStart,walkEnd);
if (!walkSource.includes('stairClearanceAllows('))
  walkSource=walkSource.replace('f === null ||','f === null || !stairClearanceAllows(x, z, feet) ||');
const blockers=[...source.matchAll(/obstacle\(([\d., \-]+)\)/g)].map(m=>{
  const [x,z,w,d,level=0]=m[1].split(',').map(Number);
  return {x0:x-w/2-.16,x1:x+w/2+.16,z0:z-d/2-.16,z1:z+d/2+.16,level};
});
const lowerCabinetFixture=createLowerKitchenCabinet(T,{RoundedBoxGeometry,mergeGeometries,oak:new T.MeshStandardMaterial(),brass:new T.MeshStandardMaterial()});
const canWalk=new Function('STEP','blockers','streetAccessAllows','photographedExterior','balconyAllows','balconyDoor','frontDoorAllows','frontDoorGroup','bathroomAllows','bathDoor','stairClearanceAllows','upperCabinetDoors','lowerCabinetDoors','staticBodyAllows','rigidPots','showerSupportHeight','rigidBoundaryBoxes',
  walkSource+'; return canWalk;')({x0:-.2,x1:.8,zBottom:2.55,zTop:-1.7},blockers,streetAccessAllows,{gateAngle:-Math.PI*.53},balconyAllows,{openness:1},frontDoorAllows,{rotation:{y:-Math.PI*.48}},bathroomAllows,{position:{z:2.3}},allows,null,lowerCabinetFixture,staticBodyAllows,[],showerSupportHeight,[]);
assert.equal(canWalk(.81,-.5,0),false,'Actual reachable near-plane regression');
assert.equal(canWalk(1,1.3,0),false,'Actual visitor gate protects above-eye head/rail contact');
assert.equal(canWalk(-.05,.85,1.2),false,'Actual visitor gate protects above-eye loft corner');
assert.equal(canWalk(-.035,.85,1.2),true,'Clear near-edge ramp position is preserved');
for (const x of [.96,1,1.2,1.5]) assert.equal(canWalk(x,-.5,0),true,'Desk-side aisle stays open');
for (let i=0;i<=100;i++) {
  const z=A.bottom-(A.bottom-A.top)*i/100;
  assert.equal(canWalk(.3,z,A.rise*i/100),true,'Actual canWalk centre stair route');
}

// Drive the current HomeWorld, including continuous interpolation and seats.
// Selection is controlled here; this tests movement, not autonomous choice.
const trace=JSON.parse(execFileSync(process.env.SUB01_TEST_PYTHON || 'python3',['-c',`
import json
from home_world import HomeWorld, NODES, DESTINATIONS
trace=[]
for origin in NODES:
    for activity in DESTINATIONS:
        h=HomeWorld({'node':origin,'seated':0})
        for i in range(2500):
            h.update(.05,.05,{'activity':activity},{})
            trace.append([origin,activity,h.position[:]])
            if h.activity_ready(activity): break
        assert h.activity_ready(activity), (origin,activity)
print(json.dumps(trace))
`],{cwd:new URL('../../',import.meta.url),encoding:'utf8',maxBuffer:32*1024*1024}));
for (const [origin,activity,p] of trace)
  assert.equal(allows(p[0],p[2],p[1]-1.65),true,`${origin} -> ${activity}: ${p}`);
console.log(`Stair clearance: actual 34 meshes, near-plane ray, boundaries and ${trace.length} real HomeWorld samples passed`);
// The actual visitor gate must reject an opened lower door in the otherwise
// clear front aisle, while keeping an adjacent walkable point available.
lowerCabinetFixture.setTargets([false,false,false,true]);
for(let i=0;i<180;i++)lowerCabinetFixture.update(1/60);
assert.equal(canWalk(-1.525,-2.8,0),false,'Visitor cannot walk knees/body into the open lower door');
assert.equal(canWalk(-1.26,-2.8,0),true,'Adjacent clear kitchen aisle remains open');
console.log('PASS: actual visitor movement includes open lower-door clearance, without sealing its adjacent aisle');
