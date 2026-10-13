import assert from 'node:assert/strict';
import * as T from 'three';
import {cabinetDoorBlocksCapsule,cabinetSweepIsClear,attachUpperCabinetDoors,CABINET_DOOR_POLICY as P} from '../../web/house/cabinet_doors.mjs';
const hinge=[-2.2,2.05,-3.545];
assert.equal(cabinetDoorBlocksCapsule(hinge,0,[-1.8,1.65,-3.10]),false);
assert.equal(cabinetDoorBlocksCapsule(hinge,-Math.PI/2,[-2.2,1.65,-3.10]),true);
assert.equal(cabinetDoorBlocksCapsule(hinge,-Math.PI/2,[-2.2,1.30,-3.10],0,.16,1.6),false,'seated body is below upper cabinet');
assert.equal(cabinetSweepIsClear(hinge,0,P.openAngle,[[-1.8,1.65,-3.10]]),false,'sweep protects standing body although initial rectangle is clear');
assert.equal(cabinetSweepIsClear(hinge,0,P.openAngle,[[-1.8,1.65,-2.0]]),true);
const root=new T.Group();root.position.set(-2.2,2.05,-3.71);
for(let i=1;i<=4;i++){
 const leaf=new T.Mesh(new T.BoxGeometry(.771,.66,.018).translate(.771/2,0,0),new T.MeshStandardMaterial());leaf.name='Cabinet door '+i;leaf.position.set(-1.548+(i-1)*.775,0,.165);
 const pull=new T.Mesh(new T.BoxGeometry(.17,.008,.008),new T.MeshStandardMaterial());pull.position.set(.5555,-.275,.011);pull.name='Cabinet brass pull '+i;leaf.add(pull);root.add(leaf);
}
root.updateMatrixWorld(true);const originalPositions=root.children.map(o=>o.getWorldPosition(new T.Vector3()).toArray());const interactions=[];let positions=[[-1.8,1.65,-2]];
const targets=[false,false,false,false];
const controller=attachUpperCabinetDoors(T,root,{interactions,getPositions:()=>positions,onToggle:(i,open)=>{targets[i]=open;controller.setTargets(targets);return true;}});assert.equal(interactions.length,4);assert.throws(()=>controller.setTargets([1,0,0,0]),TypeError);
root.updateMatrixWorld(true);assert.deepEqual(controller.doors.map(d=>d.panel.getWorldPosition(new T.Vector3()).toArray()),originalPositions,'closed appearance unchanged');
assert(controller.doors.every(d=>d.leaf.userData.excludeStaticBake&&d.panel.children[0].userData.excludeStaticBake));
assert(interactions[0].fn());for(let i=0;i<180;i++)controller.update(1/60);assert.equal(controller.doors[0].angle,P.openAngle);
root.updateMatrixWorld(true);const pull=controller.doors[0].panel.children[0].getWorldPosition(new T.Vector3());assert(pull.z>-3.1,'pull follows real hinge outside');
positions=[[-3.748,1.65,-3.1]];assert.equal(interactions[0].fn(),false,'closing refuses to sweep through visitor');
console.log('PASS: correct edge pivots, parented handles, capsule-safe continuous open/close sweep, seated height clearance, unchanged closed geometry and bake exclusion.');
