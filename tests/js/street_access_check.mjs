import assert from 'node:assert/strict';
import fs from 'node:fs';
import {execFileSync} from 'node:child_process';
import * as T from '../../web/house/vendor/three.module.js';
import {createResidentialForeground} from '../../web/house/residential_foreground.mjs';
import {STREET_ACCESS as A,streetAccessAllows as allows,streetGateAllows,buildCourtyardFrontRail} from '../../web/house/street_access.mjs';
import {balconyAllows} from '../../web/house/balcony_access.mjs';
import {frontDoorAllows} from '../../web/house/front_door_access.mjs';
import {bathroomAllows} from '../../web/house/bathroom_access.mjs';
import {stairClearanceAllows} from '../../web/house/stair_clearance.mjs';
const scene=new T.Scene();const frontage=createResidentialForeground(T,scene,{gateOpen:true});
buildCourtyardFrontRail((a,b,r)=>{
 const direction=new T.Vector3(...b).sub(new T.Vector3(...a));
 const mesh=new T.Mesh(new T.CylinderGeometry(r,r,direction.length(),8),new T.MeshStandardMaterial());
 mesh.position.copy(new T.Vector3(...a).add(new T.Vector3(...b)).multiplyScalar(.5));
 mesh.quaternion.setFromUnitVectors(new T.Vector3(0,1,0),direction.normalize());scene.add(mesh);
},new T.MeshStandardMaterial());
scene.updateMatrixWorld(true);
// Actual existing instanced pillar/fence/hinged gate plus new physical rail.
// Test a body cylinder at 17 radial offsets and 5 heights for real mesh overlap.
const bodySafe=(x,z)=>{
 const ray=new T.Raycaster();
 for(const y of [.2,.45,.65,.9,1.1]) {
  for(let angle=0;angle<Math.PI*2;angle+=Math.PI/8) {
   const direction=new T.Vector3(Math.cos(angle),0,Math.sin(angle));
   ray.set(new T.Vector3(x,y,z),direction);ray.far=A.radius;
   assert.equal(ray.intersectObjects(scene.children,true).length,0,`Body collision ${x},${z},${y}`);
  }
 }
};
for(let i=0;i<=200;i++) {
 const z=5.25+i*2/200;assert.equal(allows(2,z,frontage.gate.rotation.y),true);bodySafe(2,z);
}
for(const x of [1.59,1.62,2.41])for(let z=5.5;z<6.53;z+=.01) {
 if(allows(x,z,frontage.gate.rotation.y))bodySafe(x,z);
}
assert.equal(allows(2,5.75),true);assert.equal(allows(1.1,5.75),false,'Solid rail remains solid');
assert.equal(allows(2,6.25,0),false,'Real closed gate blocks entry');
assert.equal(allows(2,8.61),false,'Road is outside bounded walkable sidewalk');
assert.equal(allows(4,7.25),false,'No walking into static photographed buildings');
const source=fs.readFileSync(new URL('../../web/house/home.js',import.meta.url),'utf8');
const start=source.indexOf('function floorAt('),end=source.indexOf('document.getElementById("follow").onclick',start);
const code=source.slice(start,end);
assert.ok(code.includes('!streetAccessAllows('),'Actual visitor-access hook wired');
assert.ok(source.includes('buildCourtyardFrontRail(beam, M.black);'),'Actual physical front rail split');
assert.ok(!source.includes('beam([.80,.9,5.75],[3.20,.9,5.75]'),'Old solid rail removed');
const blockers=[...source.matchAll(/obstacle\(([\d., \-]+)\)/g)].map(m=>{
 const [x,z,w,d,level=0]=m[1].split(',').map(Number);
 return {x0:x-w/2-.16,x1:x+w/2+.16,z0:z-d/2-.16,z1:z+d/2+.16,level};
});
const canWalk=new Function('STEP','blockers','streetAccessAllows','photographedExterior','balconyAllows','balconyDoor','frontDoorAllows','frontDoorGroup','bathroomAllows','bathDoor','stairClearanceAllows',
 code+';return canWalk;')({x0:-.2,x1:.8,zBottom:2.55,zTop:-1.7},blockers,allows,{gateAngle:frontage.gate.rotation.y},balconyAllows,{openness:1},frontDoorAllows,{rotation:{y:-Math.PI*.48}},bathroomAllows,{position:{z:2.3}},stairClearanceAllows);
for(let i=0;i<=400;i++) assert.equal(canWalk(2,3.2+i*4.05/400,0),true,'Real visitor canWalk with implemented street hook');
assert.equal(canWalk(2,8.61,0),false);
const mesh=frontage.gateLeaf;
assert.equal(mesh.count,13);
assert.equal(frontage.gate.position.z,A.gateZ);assert.equal(frontage.gate.position.x,A.gateX);
for(const angle of [0,-.5,-1,-Math.PI*.53])
 for(const t of [.05,.5,.95])
  assert.equal(streetGateAllows(A.gateX+t*A.gateWidth*Math.cos(angle),A.gateZ-t*A.gateWidth*Math.sin(angle),angle),false);

// Run current HomeWorld's implemented route, including return from the street.
const trace=JSON.parse(execFileSync(process.env.SUB01_TEST_PYTHON||'python3',['-c',`
import json
from home_world import HomeWorld,NODES
assert NODES['outside']==(2,1.65,7.25)
h=HomeWorld({'node':'desk','seated':1});trace=[]
for activity in ['park','research']:
 for i in range(2500):
  h.update(.05,.05,{'activity':activity},{})
  if h.position[2]>3.76:trace.append(h.position[:])
  if h.activity_ready(activity):break
 assert h.activity_ready(activity)
print(json.dumps(trace))
`],{cwd:new URL('../../',import.meta.url),encoding:'utf8'}));
for(const p of trace)assert.equal(allows(p[0],p[2]),true,`Actual actor route ${p}`);
// Existing real foreground slab constructor supplies sidewalk at y=0, z5.7..8.8.
const exterior=fs.readFileSync(new URL('../../web/house/exterior_backdrops.mjs',import.meta.url),'utf8');
assert.ok(exterior.includes('slab(18,.16,3.1,0,-.08,7.25,pavement)'));
console.log(`PASS implemented street access: real frontage triangles/body clearance, bounded visitor route, ${trace.length} current HomeWorld outside/return samples`);
