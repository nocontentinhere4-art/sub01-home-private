import assert from 'node:assert/strict';
import fs from 'node:fs';
import * as T from '../../web/house/vendor/three.module.js';
import {RoundedBoxGeometry} from '../../web/house/vendor/RoundedBoxGeometry.js';
import {staticBodyAllows,showerSupportHeight,rigidBoxesFromInstances,STATIC_BODY_BOXES} from '../../web/house/static_clearance.mjs';
import {createInteriorTrim} from '../../web/house/interior_trim.mjs';
import {stairClearanceAllows} from '../../web/house/stair_clearance.mjs';
import {streetAccessAllows} from '../../web/house/street_access.mjs';
import {frontDoorAllows} from '../../web/house/front_door_access.mjs';
import {bathroomAllows} from '../../web/house/bathroom_access.mjs';
import {balconyAllows} from '../../web/house/balcony_access.mjs';
import {lowerCabinetFixture} from './lower_cabinet_fixture.mjs';
const source=fs.readFileSync(new URL('../../web/house/home.js',import.meta.url),'utf8');
const scene=new T.Scene(),material=new T.MeshStandardMaterial();
const M={wood:material,darkwood:material.clone(),kitchenOak:material.clone(),architectureOak:material.clone()};
const boxSource=source.slice(source.indexOf('function box('),source.indexOf('function cylinder('));
const box=new Function('T','RoundedBoxGeometry','M','scene','cleanKitchenBoxUv','metricBoxUv','let meshCount=0;'+boxSource+';return box;')(T,RoundedBoxGeometry,M,scene,()=>{},()=>{});
const document={createElement:()=>({width:0,height:0,getContext:()=>new Proxy({}, {get:(target,key)=>target[key]??(()=>{})})})};
const frameSource=source.slice(source.indexOf('function frame('),source.indexOf('// Architecture: loft'));
const frame=new Function('box','M','document','T','scene',frameSource+';return frame;')(box,M,document,T,scene);
new Function('frame',source.match(/^frame\(-2\.2, 4\.65, -3\.88[^\n]+/m)[0])(frame);
scene.updateMatrixWorld(true);
const ray=new T.Raycaster(new T.Vector3(-2.2,4.65,-3.725),new T.Vector3(0,0,-1),0,.16);
const hit=ray.intersectObjects(scene.children)[0];
assert(hit && hit.object.geometry.type==='PlaneGeometry','Actual foremost art plane is reached before backing');
assert(Math.abs(hit.point.z-(-3.859))<1e-6 && Math.abs(hit.distance-.134)<1e-6);
const actualBounds=new T.Box3().setFromObject(scene),policy=STATIC_BODY_BOXES.find(b=>b.name==='Loft wall art');
for(const [value,expected] of [[actualBounds.min.x,policy.x0],[actualBounds.max.x,policy.x1],
 [actualBounds.min.y,policy.low],[actualBounds.max.y,policy.high],[actualBounds.min.z,policy.z0],[actualBounds.max.z,policy.z1]])
 assert(Math.abs(value-expected)<1e-6,'Measured envelope follows real frame geometry');

const start=source.indexOf('function floorAt('),end=source.indexOf('document.getElementById("follow").onclick',start);
const blockers=[...source.matchAll(/obstacle\(([\d., \-]+)\)/g)].map(m=>{
 const[x,z,w,d,level=0]=m[1].split(',').map(Number);return{x0:x-w/2-.16,x1:x+w/2+.16,z0:z-d/2-.16,z1:z+d/2+.16,level};
});
const bed=blockers.find(b=>b.level===1&&b.x0<-3&&b.x1>-1.4&&b.z0<-3.5&&b.z1<-1);
assert(bed && -3.725<bed.z0,'The proven art contact is behind the bed blocker, not inside it');
const boundaries=rigidBoxesFromInstances(T,createInteriorTrim(T,new T.Scene()));
const canWalk=new Function('STEP','blockers','streetAccessAllows','photographedExterior','balconyAllows','balconyDoor','frontDoorAllows','frontDoorGroup','bathroomAllows','bathDoor','stairClearanceAllows','upperCabinetDoors','lowerCabinetDoors','staticBodyAllows','rigidPots','showerSupportHeight','rigidBoundaryBoxes',
 source.slice(start,end)+';return canWalk;')({x0:-.2,x1:.8,zBottom:2.55,zTop:-1.7},blockers,streetAccessAllows,{gateAngle:-Math.PI*.53},balconyAllows,{openness:1},frontDoorAllows,{rotation:{y:-Math.PI*.48}},bathroomAllows,{position:{z:2.3}},stairClearanceAllows,null,lowerCabinetFixture(),staticBodyAllows,[],showerSupportHeight,boundaries);
assert.equal(canWalk(-2.2,-3.75,3),false,'Initial suggested point remains protected by existing trim');
assert.equal(canWalk(-2.2,-3.725,3),false,'New collider protects reachable .134m triangle contact');
assert.equal(canWalk(-2.2,-3.70,3),false,'One-millimetre art overlap is still refused');
for(let x=-2.2;x<=-1.2;x+=.01)assert.equal(canWalk(x,-3.69,3),true,'Actual narrow aisle behind bed remains usable');
ray.set(new T.Vector3(-2.2,4.65,-3.69),new T.Vector3(0,0,-1));
assert.equal(ray.intersectObjects(scene.children).length,0,'Valid aisle has positive real-triangle separation');
assert.equal(staticBodyAllows(-2.2,-3.725,0),true,'Art high on loft wall never seals ground floor');
assert.equal(canWalk(-1.5,-3.725,3),true,'Unrelated rear-wall span remains unchanged');
console.log('PASS: real reachable loft-art triangle contact blocked, measured backing/plane envelope, bed clearance and narrow return aisle preserved.');
