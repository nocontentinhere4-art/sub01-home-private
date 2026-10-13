import assert from 'node:assert/strict';
import * as T from 'three';
import {RoundedBoxGeometry} from '../../web/house/vendor/RoundedBoxGeometry.js';
import {mergeGeometries} from '../../web/house/vendor/BufferGeometryUtils.js';
import {cleanKitchenBoxUv} from '../../web/house/clean_oak_material.mjs';
import {staticBakeScene} from '../../web/house/balcony_access.mjs';
import {createLowerKitchenCabinet,lowerDoorSweepClear,LOWER_CABINET as P} from '../../web/house/lower_kitchen_cabinet.mjs';
const oak=new T.MeshStandardMaterial(),brass=new T.MeshStandardMaterial(),interactions=[],positions=[[-1.8,1.65,-2]],requests=[];
const c=createLowerKitchenCabinet(T,{RoundedBoxGeometry,mergeGeometries,oak,brass,interactions,getPositions:()=>positions,onToggle:(i,open)=>{requests.push([i,open]);return true;}});
const scene=new T.Scene();scene.add(c.root);scene.updateMatrixWorld(true);
assert.equal(interactions.length,4);assert.throws(()=>c.setTargets([true]),TypeError);
for(let i=0;i<4;i++){
 const d=c.doors[i],x=P.centers[i];assert.equal(d.leaf.material,oak);assert.equal(d.pull.material,brass);
 const expected=new RoundedBoxGeometry(.65,.76,.035,2,.006);cleanKitchenBoxUv(expected,[x,.44,-3.215]);
 assert.deepEqual(Array.from(d.leaf.geometry.attributes.position.array),Array.from(expected.attributes.position.array));
 assert.deepEqual(Array.from(d.leaf.geometry.attributes.uv.array),Array.from(expected.attributes.uv.array));
 const p=d.leaf.getWorldPosition(new T.Vector3());assert(p.distanceTo(new T.Vector3(x,.44,-3.215))<1e-12);
 assert(d.pull.getWorldPosition(new T.Vector3()).distanceTo(new T.Vector3(x,.75,-3.18))<1e-12);
}
const bounds=new T.Box3().setFromObject(c.carcass);assert(Math.abs(bounds.min.x+3.725)<1e-6);assert(Math.abs(bounds.max.x+.675)<1e-6);assert(Math.abs(bounds.max.y-.8675)<1e-6);assert(bounds.min.z>=-3.86-1e-6&&bounds.max.z<=-3.24+1e-6);
const ray=new T.Raycaster(new T.Vector3(-3.3,.56,-2.8),new T.Vector3(0,0,-1));
const closed=ray.intersectObjects(c.root.children,true)[0];assert.equal(closed.object,c.doors[0].leaf);
assert(interactions[0].fn());assert.deepEqual(requests,[[0,true]]);assert.equal(c.doors[0].target,0,'waits for authoritative shared state');
c.setTargets([true,false,false,false]);for(let i=0;i<180;i++)c.update(1/60);scene.updateMatrixWorld(true);
const open=ray.intersectObjects(c.root.children,true)[0];assert.equal(open.object,c.carcass);assert(open.distance>closed.distance+.5,'real hollow cavity is visible after opening');
assert(!lowerDoorSweepClear(c.doors[0].hinge,0,P.angle,[[-3.30,1.65,-2.95]]),'opening refuses to sweep knees/body');
assert(c.allowsPosition(-.45,-2.5));assert(c.allowsPosition(-1.8,-1.05),'existing corridor and sofa approach clear');
const baked=[];staticBakeScene(scene).traverse(o=>{if(o.isMesh)baked.push(o.name);});assert.deepEqual(baked,['Lower_cabinet_carcass']);
console.log('PASS: original fronts/handles/world UV identical, footprint preserved and physical slab supported, real cavity revealed, shared targets, safe swept capsule and static-bake exclusion.');
