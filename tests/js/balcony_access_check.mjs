import assert from 'node:assert/strict';
import fs from 'node:fs';
import {execFileSync} from 'node:child_process';
import * as T from '../../web/house/vendor/three.module.js';
import {GLTFExporter} from '../../web/house/vendor/GLTFExporter.js';
import {GLTFLoader} from '../../web/house/vendor/GLTFLoader.js';
import {terraceAllows} from '../../web/house/terrace_space.mjs';
import {bathroomAllows} from '../../web/house/bathroom_access.mjs';
import {frontDoorAllows} from '../../web/house/front_door_access.mjs';
import {BALCONY_ACCESS as A,balconyAllows,balconyApproach,createBalconyDoor,staticBakeScene} from '../../web/house/balcony_access.mjs';

assert.equal(balconyAllows(-2,3.85,3,0),false,'old centre mullion route is blocked while door is closed');
assert.equal(balconyAllows(A.centre,3.85,3,.4),false,'intent/partial opening is insufficient');
assert.equal(balconyAllows(A.centre,3.85,3,1),true);
for(const x of [-3.5,-2.8,-1.5,-.5]) assert.equal(balconyAllows(x,3.85,3,1),false,'fixed sidelights cannot be crossed');
assert.equal(balconyAllows(A.centre,3.85,3,NaN),false);
assert.equal(balconyAllows(A.centre,3.85,0,0),true,'ground-floor entrance is independent');
assert.equal(balconyApproach([A.centre,4.65,3.2]),true);
assert.equal(balconyApproach([A.centre,1.65,3.2]),false);
assert.equal(balconyApproach([2,4.65,-3]),false);

// Exercise the actual visitor floor/collision function, not just a new helper.
const source=fs.readFileSync(new URL('../../web/house/home.js',import.meta.url),'utf8');
const start=source.indexOf('function floorAt('),end=source.indexOf('document.getElementById("follow").onclick',start);
const blockers=[...source.matchAll(/obstacle\(([\d., \-]+)\)/g)].map(m=>{
  const [x,z,w,d,level=0]=m[1].split(',').map(Number);
  return {x0:x-w/2-.16,x1:x+w/2+.16,z0:z-d/2-.16,z1:z+d/2+.16,level};
});
const collisionDoor={openness:0};
const canWalk=new Function('STEP','blockers','terraceAllows','balconyAllows','balconyDoor','frontDoorAllows','frontDoorGroup','bathroomAllows','bathDoor',
  source.slice(start,end)+'; return canWalk;')({x0:-.2,x1:.8,zBottom:2.55,zTop:-1.7},blockers,terraceAllows,balconyAllows,collisionDoor,frontDoorAllows,{rotation:{y:-Math.PI*.48}},bathroomAllows,{position:{z:2.3}});
assert.equal(canWalk(-2,3.85,3),false);
collisionDoor.openness=1;
assert.equal(canWalk(A.centre,3.85,3),true);
assert.equal(canWalk(-3.5,3.85,3),false);
assert.equal(canWalk(-.5,3.85,3),false);
assert.equal(canWalk(2,3.95,0),true,'existing ground front-door route remains available');

const scene=new T.Scene(),door=createBalconyDoor(T,scene,new T.MeshStandardMaterial());
const ids=new T.Mesh(new T.BoxGeometry(1,1,1),new T.MeshStandardMaterial());
ids.userData.bakeId='house-static-preserved';scene.add(ids);
let last=door.leaf.position.x, ticks=0;
while(door.update(.05,true)) {
  assert.ok(door.leaf.position.x-last<=.85*.05+1e-10,'bounded real sliding speed');
  last=door.leaf.position.x;assert.ok(++ticks<100);
}
assert.ok(door.openness>.999);assert.ok(ticks*.05>1.2 && ticks*.05<2.5);
const original=door.leaf.position.toArray(), originalVisible=door.leaf.visible;
const bake=staticBakeScene(scene);
assert.equal(bake.getObjectByName('balcony_sliding_leaf'),undefined);
assert.ok(bake.getObjectByName('balcony_fixed_sidelight_frames'));
assert.ok(bake.children.some(o=>o.userData.bakeId==='house-static-preserved'));
assert.deepEqual(door.leaf.position.toArray(),original);assert.equal(door.leaf.visible,originalVisible);
// Round-trip actual instanced frame geometry through the same exporter used
// by the private bake workflow. The original runtime leaf remains untouched.
globalThis.FileReader=class {
  readAsArrayBuffer(blob){blob.arrayBuffer().then(buffer=>{this.result=buffer;this.onloadend?.();});}
};
const binary=await new GLTFExporter().parseAsync(bake,{binary:true,onlyVisible:true});
const restored=(await new GLTFLoader().parseAsync(binary,'')).scene;
let instanceCount=0;
restored.traverse(object=>{if(object.name==='balcony_fixed_sidelight_frames' && object.isInstancedMesh) instanceCount+=object.count;});
assert.equal(instanceCount,8,'all fixed doorway/sidelight frame pieces survive the static GLB export');
assert.equal(restored.getObjectByName('balcony_sliding_leaf'),undefined);
for(let i=0;i<100;i++) door.update(.05,false);
assert.ok(door.openness<1e-10);assert.equal(balconyAllows(A.centre,3.85,3,door.openness),false);

// The existing actor route approaches from the side before crossing the
// facade. Its real sensor must open far enough before reaching the slab.
const routed=createBalconyDoor(T,new T.Scene(),new T.MeshStandardMaterial());
const legs=[[-.5,3.2],[-2.2,3.2],[-2.2,4.4]];
for(let leg=1;leg<legs.length;leg++) {
  const from=legs[leg-1],to=legs[leg],distance=Math.hypot(to[0]-from[0],to[1]-from[1]);
  const steps=Math.ceil(distance/(1.25*.05));
  for(let i=0;i<=steps;i++) {
    const f=i/steps,x=from[0]+(to[0]-from[0])*f,z=from[1]+(to[1]-from[1])*f;
    routed.update(.05,balconyApproach([x,4.65,z]));
    assert.ok(balconyAllows(x,z,3,routed.openness),'existing x=-2.2 actor route crosses only after physical clearance');
  }
}
// Use the actual Python HomeWorld movement implementation, including its
// getting-up stage, waypoints, acceleration and braking. A held 5 Hz feed is
// the conservative case when the visitor camera is elsewhere in the house.
const trace=JSON.parse(execFileSync(process.env.SUB01_TEST_PYTHON || 'python3',['-c',`
import json
from home_world import HomeWorld
h=HomeWorld({'node':'bed','seated':1})
trace=[]
for activity in ['window','research']:
    for i in range(2000):
        h.update(.05,.05,{'activity':activity}, {})
        trace.append(h.view()['position'])
        if not h.path and h.node==h.desired(activity): break
    assert h.node==h.desired(activity)
print(json.dumps(trace))
`],{cwd:new URL('../../',import.meta.url),encoding:'utf8'}));
const actual=createBalconyDoor(T,new T.Scene(),new T.MeshStandardMaterial());
let crossings=0;
for(let i=0;i<trace.length;i++) {
  actual.update(.05,balconyApproach(trace[Math.floor(i/4)*4]));
  const [x,y,z]=trace[i];
  assert.ok(balconyAllows(x,z,y-1.65,actual.openness),`actual actor crossed closed glass at tick ${i}`);
  if(z>3.7 && z<4.0) crossings++;
}
assert.ok(crossings>6 && trace.some(p=>p[2]===4.4) && trace.at(-1)[2]===-.75);
console.log('PASS: closed/fixed glass collision, physical leaf clearance, actor approach, bounded door speed, lite-compatible geometry and dynamic-bake exclusion');
