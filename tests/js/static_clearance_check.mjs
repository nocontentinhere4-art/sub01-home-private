import assert from 'node:assert/strict';
import fs from 'node:fs';
import {execFileSync} from 'node:child_process';
import * as T from '../../web/house/vendor/three.module.js';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {staticBodyAllows,rigidPotFromMesh,rigidBoxFromMesh,rigidBoxesFromInstances,showerSupportHeight,STATIC_BODY_BOXES} from '../../web/house/static_clearance.mjs';
import {createInteriorTrim} from '../../web/house/interior_trim.mjs';
import {stairClearanceAllows} from '../../web/house/stair_clearance.mjs';
import {streetAccessAllows} from '../../web/house/street_access.mjs';
import {frontDoorAllows} from '../../web/house/front_door_access.mjs';
import {bathroomAllows} from '../../web/house/bathroom_access.mjs';
import {balconyAllows} from '../../web/house/balcony_access.mjs';
import {createLowerKitchenCabinet} from '../../web/house/lower_kitchen_cabinet.mjs';
import {RoundedBoxGeometry} from '../../web/house/vendor/RoundedBoxGeometry.js';
import {mergeGeometries} from '../../web/house/vendor/BufferGeometryUtils.js';
const source=fs.readFileSync(new URL('../../web/house/home.js',import.meta.url),'utf8');
const material=new T.MeshStandardMaterial(),scene=new T.Scene();
const rigidBoundaryBoxes=[];
const M={darkwood:material,architectureOak:material,brass:material};
const beamSource=source.slice(source.indexOf('function beam('),source.indexOf('function obstacle('));
const beam=new Function('T','scene','M','metricCylinderUv','rigidBoundaryBoxes','rigidBoxFromMesh',beamSource+';return beam;')(T,scene,M,()=>{},rigidBoundaryBoxes,rigidBoxFromMesh);
const guardStart=source.indexOf('for (let z = -3.8; z < -1.7; z += 0.35)');
new Function('beam','M',source.slice(guardStart,source.indexOf('const aoCanvas',guardStart)))(beam,M);
assert.equal(rigidBoundaryBoxes.length,7,'Six actual landing posts plus top rail registered separately');
assert.equal(staticBodyAllows(.74,-3.4,3,[],rigidBoundaryBoxes),false,'Actual right landing post triangle witness is protected');
assert.equal(staticBodyAllows(.3,-2.1,3,[],rigidBoundaryBoxes),true,'Centre landing route remains open');
assert.equal(staticBodyAllows(.74,-3.4,0,[],rigidBoundaryBoxes),true,'Landing guard does not become a downstairs wall');
const frameSource=source.slice(source.indexOf('function windowFrame('),source.indexOf('for (const z of [-2.6, 0, 2.6])'));
const frame=new Function('T','scene','M','rigidBoundaryBoxes','rigidBoxFromMesh',frameSource+';return windowFrame;')(T,scene,M,rigidBoundaryBoxes,rigidBoxFromMesh);
frame(-3.85,1.7,0,2.48,2.02,true);
assert.equal(staticBodyAllows(-3.70,0,0,[],rigidBoundaryBoxes),false,'Real projecting window mullion protects body below eye');
assert.equal(staticBodyAllows(-3.60,0,0,[],rigidBoundaryBoxes),true,'Empty adjacent aisle remains usable');
assert.equal(staticBodyAllows(-3.70,0,3,[],rigidBoundaryBoxes),true,'Window below does not seal the loft');
const trim=createInteriorTrim(T,scene);
const trimBoxes=rigidBoxesFromInstances(T,trim);rigidBoundaryBoxes.push(...trimBoxes);
assert.equal(trimBoxes.length,20,'Every actual trim instance stays a narrow independent box');
assert.equal(staticBodyAllows(.5,-3.75,0,[],trimBoxes),false,'Rounded foot clears actual rear quarter-round protrusion');
const boxes=[];
function box(w,h,d,x,y,z) {
  const mesh=new T.Mesh(new T.BoxGeometry(w,h,d),material);mesh.position.set(x,y,z);scene.add(mesh);boxes.push(mesh);return mesh;
}
// Execute the actual TV backing and shower construction lines, not helper dimensions.
for(const line of [source.match(/box\(0\.14, 2\.8, 2\.15[^\n]+/)[0],source.match(/box\(0\.025, 2, 1[^\n]+/)[0],source.match(/box\(0\.9, 0\.1, 1[^\n]+/)[0]])
  new Function('box','M','showerGlass','tiles',line)(box,{wall:material},material,material);
scene.updateMatrixWorld(true);
const ray=new T.Raycaster();ray.far=.16;
ray.set(new T.Vector3(-3.70,1.25,.99),new T.Vector3(-1,0,0));
assert(ray.intersectObjects(scene.children)[0],'Before: real TV backing lies within body radius');
assert.equal(staticBodyAllows(-3.70,.99,0),false);
assert.equal(staticBodyAllows(-3.60,.99,0),true,'Adjacent lounge/table circulation remains open');
ray.set(new T.Vector3(-2.08,3.45,2),new T.Vector3(1,0,0));
assert(ray.intersectObjects(scene.children)[0],'Before: real shower glass lies within body radius');
assert.equal(staticBodyAllows(-2.08,2,3),false);
assert.equal(staticBodyAllows(-1.5,2,3.13),true,'Shower remains enterable from its actual open side');
assert.equal(staticBodyAllows(-1.5,1.35,3),true,'Actual bathroom waypoint is unchanged');
assert.equal(showerSupportHeight(-1.5,2),3.13);
const shelfData=fs.readFileSync(new URL('../../web/house/assets/office-shelves-original/shelves.glb',import.meta.url));
const shelf=(await new GLTFLoader().parseAsync(shelfData.buffer.slice(shelfData.byteOffset,shelfData.byteOffset+shelfData.byteLength),'')).scene;
shelf.position.set(2.125,0,-3.72);shelf.updateMatrixWorld(true);
const shelfBounds=new T.Box3().setFromObject(shelf),policy=STATIC_BODY_BOXES.find(b=>b.name==='Office oak shelves');
for(const [actual,expected] of [[shelfBounds.min.x,policy.x0],[shelfBounds.max.x,policy.x1],[shelfBounds.min.z,policy.z0],[shelfBounds.max.z,policy.z1]])
  assert(Math.abs(actual-expected)<.002,'Collider footprint follows actual original office asset');

// Fit the original full/lite pot mesh exactly as furnished() does, including
// all leaves in the fit bounds. No textures are loaded or third-party network used.
globalThis.ProgressEvent??=class ProgressEvent {constructor(type,options){Object.assign(this,{type},options);}};
async function loadPot(lite=false) {
  const directory=new URL('../../web/house/assets/'+(lite?'lite/':'')+'potted_plant_01/',import.meta.url);
  const json=JSON.parse(fs.readFileSync(new URL('potted_plant_01_leaf_lod.gltf',directory),'utf8'));
  for(const b of json.buffers) b.uri='data:application/octet-stream;base64,'+fs.readFileSync(new URL(b.uri,directory)).toString('base64');
  delete json.images;delete json.textures;delete json.materials;
  for(const mesh of json.meshes)for(const p of mesh.primitives)delete p.material;
  return (await new GLTFLoader().parseAsync(JSON.stringify(json),'')).scene;
}
const rigidPots=[];
for(const lite of [false,true]) {
  const model=await loadPot(lite);
  for(const [x,y,z,width] of [[-3.45,0,3.25,.7],[-3.3,3,2.7,.9*.55],[-3.4,3,4.65,1.1*.55]]) {
    const root=model.clone(true);
    let bounds=new T.Box3().setFromObject(root);root.scale.setScalar(width/bounds.getSize(new T.Vector3()).x);
    bounds=new T.Box3().setFromObject(root);const centre=bounds.getCenter(new T.Vector3());
    root.position.set(x-centre.x,y-bounds.min.y,z-centre.z);root.updateMatrixWorld(true);
    let pot=null;root.traverse(o=>{if(o.isMesh&&/potted_plant_01_pot/.test(o.name))pot=rigidPotFromMesh(T,o);});
    assert(pot && pot.radius>0 && pot.high>pot.low);
    assert.equal(staticBodyAllows(pot.x,pot.z,y,[pot]),false,'Rigid pot cannot be walked through');
    assert.equal(staticBodyAllows(pot.x+pot.radius+.161,pot.z,y,[pot]),true,'Measured cylinder preserves empty space outside pot');
    if(!lite)rigidPots.push(pot);
  }
}
const start=source.indexOf('function floorAt('),end=source.indexOf('document.getElementById("follow").onclick',start);
const blockers=[...source.matchAll(/obstacle\(([\d., \-]+)\)/g)].map(m=>{
  const[x,z,w,d,level=0]=m[1].split(',').map(Number);return{x0:x-w/2-.16,x1:x+w/2+.16,z0:z-d/2-.16,z1:z+d/2+.16,level};
});
const lower=createLowerKitchenCabinet(T,{RoundedBoxGeometry,mergeGeometries,oak:material,brass:material});
const actual=new Function('STEP','blockers','streetAccessAllows','photographedExterior','balconyAllows','balconyDoor','frontDoorAllows','frontDoorGroup','bathroomAllows','bathDoor','stairClearanceAllows','upperCabinetDoors','lowerCabinetDoors','staticBodyAllows','rigidPots','showerSupportHeight','rigidBoundaryBoxes',
  source.slice(start,end)+';return {canWalk,floorAt};')({x0:-.2,x1:.8,zBottom:2.55,zTop:-1.7},blockers,streetAccessAllows,{gateAngle:-Math.PI*.53},balconyAllows,{openness:1},frontDoorAllows,{rotation:{y:-Math.PI*.48}},bathroomAllows,{position:{z:2.3}},stairClearanceAllows,null,lower,staticBodyAllows,rigidPots,showerSupportHeight,rigidBoundaryBoxes);
assert.equal(actual.floorAt(-.16,4.16,3),null,'Former imaginary loft strip has no floor');
assert.equal(actual.canWalk(-.25,4.16,3),false,'Capsule cannot overhang actual x=-.2 slab edge');
assert.equal(actual.canWalk(-.4,4.16,3),true,'Real supported balcony corner remains usable');
assert.equal(actual.canWalk(-3.70,.99,0),false);
assert.equal(actual.canWalk(-3.76,-2.86,0),false,'Actual wall face -3.91 requires the .16m capsule margin');
assert.equal(actual.canWalk(3.76,2.5,0),false,'Mirrored solid east wall preserves the same radius');
assert.equal(actual.canWalk(1.1,-3.76,0),false,'Real office shelves behind desk are now blocked');
assert.equal(staticBodyAllows(1.1,-3.76,3),true,'Ground-floor shelving does not become a whole-level wall upstairs');
assert.equal(staticBodyAllows(-3.70,.99,3),true,'TV backing does not obstruct the floor above it');
assert.equal(actual.canWalk(-2.08,2,3),false);
assert.equal(actual.floorAt(-1.5,2,3),3.13);
ray.set(new T.Vector3(-1.5,3.4,2),new T.Vector3(0,-1,0));ray.far=.6;
assert(Math.abs(ray.intersectObjects(scene.children)[0].point.y-actual.floorAt(-1.5,2,3))<1e-6,'Positive shower support follows actual tray triangles');
let feet=3;
for(let z=1.55;z<=1.8;z+=.01) {
  assert(actual.canWalk(-1.5,z,feet),'The intentional low tray step remains accessible from its open front');
  feet=actual.floorAt(-1.5,z,feet);
}
assert.equal(feet,3.13);
const trace=JSON.parse(execFileSync(process.env.PYTHON||'python3',['-c',`
import json
from home_world import HomeWorld
h=HomeWorld({'node':'desk','seated':1});trace=[]
for activity in ['sleep','use_bathroom','window','eat','play_console','park','research']:
 for i in range(3000):
  h.update(.05,.05,{'activity':activity},{})
  if not h.seated:trace.append(h.position[:])
  if h.activity_ready(activity):break
 assert h.activity_ready(activity)
print(json.dumps(trace))
`],{cwd:new URL('../../',import.meta.url),encoding:'utf8'}));
for(const [x,y,z] of trace) assert.equal(staticBodyAllows(x,z,y-1.65,rigidPots,rigidBoundaryBoxes),true,'Real actor route remains clear of added exact colliders');
console.log('PASS: actual TV/shower triangle counterexamples rejected, full/lite rendered pot footprints, real loft support edge and '+trace.length+' standing actor route poses preserved.');
