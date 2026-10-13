import assert from 'node:assert/strict';
import fs from 'node:fs';
import * as T from '../../web/house/vendor/three.module.js';
import {staticBakeScene} from '../../web/house/balcony_access.mjs';

const source=fs.readFileSync(new URL('../../web/house/home.js',import.meta.url),'utf8');
const begin=source.indexOf('function contact('),end=source.indexOf('// Ground floor lounge:',begin);
assert.ok(begin>0&&end>begin);
const scene=new T.Scene(),aoTex=new T.Texture();
new Function('T','scene','aoTex',source.slice(begin,end))(T,scene,aoTex);
const decals=[...scene.children];assert.equal(decals.length,4);
for(const decal of decals){
  assert.ok(decal.isMesh&&decal.material.isMeshBasicMaterial&&decal.material.transparent);
  assert.equal(decal.userData.excludeStaticBake,true);
  assert.equal(decal.visible,true,'Contact shadow remains visible in the real room');
}
const floor=new T.Mesh(new T.PlaneGeometry(8,8),new T.MeshStandardMaterial());scene.add(floor);
const copy=staticBakeScene(scene);
assert.equal(copy.children.length,1,'Fake shadow decals never absorb or emit in the physical bake');
assert.equal(copy.children[0].geometry,floor.geometry,'Real physical floor remains in exported scene');
assert.equal(scene.children.length,5,'Export never removes actual live decals or floor');
assert.ok(decals.every(decal=>decal.parent===scene&&decal.visible));
console.log('PASS actual contact builder: four live visual shadow decals excluded from bake; physical floor and original scene preserved.');
