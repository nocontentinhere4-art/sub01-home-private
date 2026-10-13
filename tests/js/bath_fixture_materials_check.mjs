import assert from 'node:assert/strict';
import * as T from 'three';
import {BATH_FIXTURE_MESH_ROLES,BATH_LIGHT_DIFFUSER,GLAZED_CERAMIC,createBathFixtureMaterials,installBathFixture} from '../../web/house/bath_fixture_materials.mjs';

const oak=new T.MeshStandardMaterial({map:new T.Texture(),roughness:.92}),brass=new T.MeshStandardMaterial(),metal=new T.MeshStandardMaterial();
const materials=createBathFixtureMaterials(T,{oak,brass,metal});
assert.equal(materials.oak,oak,'shared clean oak instance, no cloned bitmap');
assert.equal(materials.brass,brass);assert.equal(materials.metal,metal);
assert(materials.ceramic.isMeshPhysicalMaterial&&materials.ceramic.roughness===GLAZED_CERAMIC.roughness&&materials.ceramic.metalness===0);
assert(materials.seat.roughness>materials.ceramic.roughness,'satin seat is softer than glaze');
assert.throws(()=>createBathFixtureMaterials(T,{oak}),/shared oak/);

// Same runtime convention as tools/build_home_bath_fixtures.py:
// Blender (0,.26,0) at the vanity back -> glTF (0,0,-.26) -> yaw +90deg -> west wall face side.
const sidecar={runtime_origin_m:[-3.645,3.0525,1.1],runtime_yaw_radians:Math.PI/2,mesh_roles:['Vanity_brass','Vanity_ceramic','Vanity_oak']};
function fixture(names){
  const root=new T.Group();
  for(const name of names){const mesh=new T.Mesh(new T.BoxGeometry(.1,.1,.1));mesh.name=name;root.add(mesh);}
  return root;
}
const root=installBathFixture(fixture(sidecar.mesh_roles),sidecar,materials);
const back=new T.Vector3(0,0,-.26).applyMatrix4(root.matrixWorld);
assert(Math.abs(back.x+3.905)<1e-9&&Math.abs(back.y-3.0525)<1e-9&&Math.abs(back.z-1.1)<1e-9,'vanity back lands 5 mm off the west wall face');
const front=new T.Vector3(0,0,.26).applyMatrix4(root.matrixWorld);
assert(front.x>back.x,'front faces into the bathroom (+X)');
root.traverse(o=>{if(o.isMesh){assert.equal(o.material,materials[BATH_FIXTURE_MESH_ROLES[o.name]]);assert(o.castShadow&&o.receiveShadow);}});
assert.throws(()=>installBathFixture(fixture(['Vanity_oak','Mystery_box']),sidecar,materials),/Unexpected/);
assert.throws(()=>installBathFixture(fixture(['Vanity_oak']),sidecar,materials),/missing: Vanity_brass/);
assert.throws(()=>installBathFixture(fixture(['Vanity_oak']),{runtime_origin_m:[0,NaN,0],runtime_yaw_radians:0},materials),/finite/);
// Bath ceiling light: switched diffuser follows the bathroom light like other lampEmission fixtures.
assert.equal(materials.diffuser.userData.lampEmission,BATH_LIGHT_DIFFUSER.lampEmission);
assert.equal(materials.diffuser.emissiveIntensity,BATH_LIGHT_DIFFUSER.lampEmission);
assert.equal(materials.diffuser.userData.switchedRoom,'bathroom');
const lamp=installBathFixture(fixture(['BathLight_oak','BathLight_diffuser']),{runtime_origin_m:[-2.6,5.95,1.55],runtime_yaw_radians:0,mesh_roles:['BathLight_diffuser','BathLight_oak']},materials);
lamp.traverse(o=>{if(o.name==='BathLight_diffuser')assert.equal(o.material,materials.diffuser);if(o.name==='BathLight_oak')assert.equal(o.material,oak);});
// Door leaf rides on the existing sliding bathDoor mesh: local origin, yaw -90deg.
const slab=new T.Mesh(new T.BoxGeometry(.065,2,.89));slab.position.set(-.85,4.05,1.35);
const leaf=installBathFixture(fixture(['Door_oak','Door_brass']),{runtime_origin_m:[0,0,0],runtime_yaw_radians:-Math.PI/2,mesh_roles:['Door_brass','Door_oak']},materials);
slab.add(leaf);slab.position.z=2.3;slab.updateMatrixWorld(true);
const edge=new T.Vector3(-.445,0,0).applyMatrix4(leaf.matrixWorld); // Blender -X (glTF -X) leading edge
assert(Math.abs(edge.x+.85)<1e-9&&Math.abs(edge.z-(2.3-.445))<1e-9,'leaf follows the slide; leading edge toward -z');
console.log('PASS: bath fixtures share oak/brass/metal, glazed ceramic + satin seat, sidecar placement matches the Blender generator convention, unknown/missing meshes rejected.');
