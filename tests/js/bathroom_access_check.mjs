import {lowerCabinetFixture} from './lower_cabinet_fixture.mjs';
import {staticBodyAllows,showerSupportHeight} from '../../web/house/static_clearance.mjs';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {execFileSync} from 'node:child_process';
import {BATHROOM_ACCESS as A, bathroomAllows, bathroomApproach, bathroomDoorPosition} from '../../web/house/bathroom_access.mjs';
import {balconyAllows} from '../../web/house/balcony_access.mjs';
import {frontDoorAllows} from '../../web/house/front_door_access.mjs';
import {streetAccessAllows} from '../../web/house/street_access.mjs';
import {stairClearanceAllows} from '../../web/house/stair_clearance.mjs';

assert.equal(bathroomApproach([-.5,4.65,1.35]),true);
assert.equal(bathroomApproach([-.5,1.65,1.35]),false);
assert.equal(bathroomApproach([2,1.65,-.75]),false);
assert.equal(bathroomAllows(A.plane,1.35,3,A.closed),false);
assert.equal(bathroomAllows(A.plane,1.35,3,1.7),false);
assert.equal(bathroomAllows(A.plane,1.35,3,A.open),true);
assert.equal(bathroomAllows(A.plane,1.35,3,NaN),false);
assert.equal(bathroomAllows(A.plane,1.35,0,A.closed),true);
for (const z of [.7,.9,1.8,2.1,2.6])
  assert.equal(bathroomAllows(A.plane,z,3,A.open),false,'Fixed walls/jambs do not disappear with open leaf');

// Exercise the actual full visitor collision function, including wall blockers.
const source=fs.readFileSync(new URL('../../web/house/home.js',import.meta.url),'utf8');
const start=source.indexOf('function floorAt('),end=source.indexOf('document.getElementById("follow").onclick',start);
const blockers=[...source.matchAll(/obstacle\(([\d., \-]+)\)/g)].map(m=>{
  const [x,z,w,d,level=0]=m[1].split(',').map(Number);
  return {x0:x-w/2-.16,x1:x+w/2+.16,z0:z-d/2-.16,z1:z+d/2+.16,level};
});
const leaf={position:{z:A.closed}};
const canWalk=new Function('STEP','blockers','streetAccessAllows','photographedExterior','balconyAllows','balconyDoor','frontDoorAllows','frontDoorGroup','bathroomAllows','bathDoor','stairClearanceAllows','upperCabinetDoors','lowerCabinetDoors','staticBodyAllows','rigidPots','showerSupportHeight','rigidBoundaryBoxes',
  source.slice(start,end)+'; return canWalk;')({x0:-.2,x1:.8,zBottom:2.55,zTop:-1.7},blockers,streetAccessAllows,{gateAngle:-Math.PI*.53},balconyAllows,{openness:1},frontDoorAllows,{rotation:{y:-Math.PI*.48}},bathroomAllows,leaf,stairClearanceAllows,null,lowerCabinetFixture(),staticBodyAllows,[],showerSupportHeight,[]);
assert.equal(canWalk(A.plane,1.35,3),false);
leaf.position.z=1.7;assert.equal(canWalk(A.plane,1.35,3),false);
leaf.position.z=A.open;assert.equal(canWalk(A.plane,1.35,3),true);
for(const z of [.7,2.1]) assert.equal(canWalk(A.plane,z,3),false);

const trace=JSON.parse(execFileSync(process.env.SUB01_TEST_PYTHON || 'python3',['-c',`
import json
from home_world import HomeWorld
h=HomeWorld({'node':'bed','seated':1})
trace=[]
for activity in ['use_bathroom','research']:
    for i in range(2000):
        h.update(.05,.05,{'activity':activity},{})
        # [real walking eye, what the page receives]: during privacy the feed
        # carries the doorway stand-in, never the actor's real pose.
        trace.append([list(h.position), h.view()['position']])
        if h.activity_ready(activity): break
    assert h.activity_ready(activity)
print(json.dumps(trace))
`],{cwd:new URL('../../',import.meta.url),encoding:'utf8'}));
let centre=A.closed, held=trace[0][1], crossed=0;
const viewer=[2,1.65,-.75];
for(let i=0;i<trace.length;i++) {
  if(i%4===0)held=trace[i][1]; // Conservative actual 5Hz published feed, viewer stays elsewhere.
  centre=bathroomDoorPosition(centre,.05,bathroomApproach(viewer)||bathroomApproach(held));
  const [x,y,z]=trace[i][0];
  if(y>3 && Math.abs(x-A.plane)<=.20 && z>.85 && z<1.8) {
    crossed++;
    assert.ok(bathroomAllows(x,z,3,centre),'Real actor crosses only after leaf is physically clear');
  }
}
assert.ok(crossed>4,'Trace really crosses the door on entry and exit');
console.log('PASS: bathroom closed/partial/fixed-wall collisions and actual bed→bathroom→desk actor route with held5Hz feed');
