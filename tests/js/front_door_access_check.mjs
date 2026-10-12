import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {FRONT_DOOR as D,frontDoorAllows,frontDoorApproach} from '../../web/house/front_door_access.mjs';
assert.equal(frontDoorAllows(2,3.9,0,0),false);
assert.equal(frontDoorAllows(2,3.9,0,-Math.PI*.48),true);
assert.equal(frontDoorAllows(D.x,D.z,0,-Math.PI*.48),false,'hinge remains solid');
assert.equal(frontDoorAllows(2,3.9,3,0),true,'upper floor independent');
for (const angle of [0,-.3,-.9,-1.5]) {
  for (const t of [0,.3,.7,1]) {
    const x=D.x+t*D.width*Math.cos(angle),z=D.z-t*D.width*Math.sin(angle);
    assert.equal(frontDoorAllows(x,z,0,angle),false,'entire rotated leaf is solid');
  }
}
assert.equal(frontDoorApproach([2,1.65,3.2]),true);
assert.equal(frontDoorApproach([2,4.65,3.2]),false);
const trace=JSON.parse(execFileSync(process.env.SUB01_TEST_PYTHON || 'python3',['-c',`
import json
from home_world import HomeWorld
h=HomeWorld({'node':'desk','seated':1})
out=[]
for activity in ['park','use_computer']:
 for i in range(4000):
  h.update(.05,.05,{'activity':activity},{})
  out.append(h.view()['position'])
  if h.activity_ready(activity):break
print(json.dumps(out))
`],{encoding:'utf8'}));
let angle=0;
for(let tick=0;tick<trace.length;tick++) {
  const p=trace[tick],held=trace[Math.floor(tick/4)*4];
  // Viewer remains upstairs: only the actor feed can trigger the door.
  const target=frontDoorApproach(held)?-Math.PI*.48:0;
  angle+=(target-angle)*.05*7;
  if(p[1]<3) assert.equal(frontDoorAllows(p[0],p[2],0,angle),true,'actual actor route clears real leaf with held 5Hz feed');
}
console.log('PASS: physical hinged leaf, hinge/body clearance, actor-only opening and real bidirectional route');
