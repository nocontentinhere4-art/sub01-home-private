import assert from 'node:assert/strict';
import fs from 'node:fs';
import * as T from 'three';
import {createHavenSofaMaterials} from '../../web/house/haven_sofa_materials.mjs';
const urls = [];
const materials = createHavenSofaMaterials(T, {load(url) {urls.push(url);return new T.Texture();}}, '/house/assets/lite/', 8);
assert.equal(urls.length,6);assert(urls.every(u=>u.startsWith('/house/assets/lite/haven-sofa/maps/')));
assert.equal(materials.Haven_linen.map.colorSpace,T.SRGBColorSpace);
assert.equal(materials.Haven_linen.normalMap.colorSpace,T.NoColorSpace);
assert.equal(materials.Haven_linen.normalScale.x,.43);
assert.equal(materials.Haven_linen.map.repeat.x,1);
for (const material of [materials.Haven_linen, materials.Haven_legs])
  for (const texture of [material.map, material.normalMap, material.roughnessMap])
    assert.equal(texture.flipY, false, 'Source glTF UV/image orientation retained');
assert.equal(materials.Haven_linen.sheen,1);
assert.equal(materials.Haven_legs.clearcoat,.18);
const metadata=JSON.parse(fs.readFileSync(new URL('../../web/house/assets/haven-sofa/sofa.json',import.meta.url)));
assert.equal(metadata.groups,4);
assert(metadata.triangles<70000);
const b=metadata.blender_bounds;
assert(b[1][0]-b[0][0]<2.5);assert(b[1][1]-b[0][1]<.95);assert(Math.abs(b[0][2])<1e-7);
console.log('PASS: licensed source PBR values, full/lite texture routes, four groups, measured geometry budget and unchanged collider fit.');
