import assert from 'node:assert/strict';
import fs from 'node:fs';
import * as T from '../../web/house/vendor/three.module.js';
import {createExteriorBackdrops} from '../../web/house/exterior_backdrops.mjs';
import {staticBakeScene} from '../../web/house/balcony_access.mjs';
let loaded=[];
class Loader{constructor(manager){this.manager=manager;}load(url){loaded.push(url);return new T.Texture();}}
const three={...T,TextureLoader:Loader};
for(const lite of [false,true]){
 const scene=new T.Scene(),legacy=new T.Group();legacy.userData.excludeStaticBake=true;scene.add(legacy);
 const view=createExteriorBackdrops(three,scene,{lite},legacy);
 assert.equal(loaded.findLast(url=>url.includes('/tokyo-residential/residential-')),`/house/assets/tokyo-residential/residential-${lite?2048:4096}.webp`);
 assert.equal(view.activate(),false);assert.equal(legacy.visible,true);
 view.texture.image={width:lite?2048:4096,height:lite?1024:2048};
 assert.equal(view.activate(),true);assert.equal(legacy.visible,false);
 assert.equal(view.sphere.material.side,T.BackSide);
 assert.equal(view.sphere.material.depthWrite,false);assert.equal(view.sphere.material.fog,false);
 assert.equal(view.sphere.geometry.type,'SphereGeometry','full spherical sky and ground, no plate bounds');
 assert.equal(view.group.userData.excludeStaticBake,true);
 assert.equal(staticBakeScene(scene).children.length,0,'street capture/paving excluded from indoor baked GI');
 const texture=view.texture;view.update(.016,12);const noon=view.sphere.material.uniforms.uBrightness.value;
 view.update(.016,0);assert.ok(view.sphere.material.uniforms.uBrightness.value<noon);
 assert.equal(view.texture,texture,'clock grading shares one texture, not second day/night download');
 assert.equal(view.state().probes,0);assert.equal(view.state().panoramaTextures,1);
}
assert.equal(loaded.filter(url=>url.includes('/tokyo-residential/residential-')).length,2,'one panorama per chosen quality');
assert.equal(loaded.length,10,'four packed PBR maps per chosen quality, no duplicate curb textures');
const home=fs.readFileSync('web/house/home.js','utf8');
assert.ok(!home.includes('sharedWindowTextures'));assert.ok(!home.includes('base: lite ? "/house/assets/lite/window/"'));
const manifest=JSON.parse(fs.readFileSync('web/house/assets/tokyo-residential/manifest.json'));
assert.equal(manifest.license,'CC BY 2.0');assert.ok(manifest.modifications.includes('historical static LDR'));
for(const asset of manifest.outputs){const bytes=fs.readFileSync('web/house/assets/tokyo-residential/'+asset.file);assert.equal(bytes.length,asset.bytes);}
console.log('PASS: one spherical residential source per quality, image-safe fallback, shared clock grading/no probes, no old finite photo loads, indoor GI exclusion and source provenance');
