import assert from 'node:assert/strict';
import fs from 'node:fs';
import crypto from 'node:crypto';
import * as T from '../../web/house/vendor/three.module.js';
import {createStreetMaterials,streetMetricUv} from '../../web/house/street_materials.mjs';
let urls=[];class TextureLoader{load(url){urls.push(url);return new T.Texture();}}
for(const lite of [false,true]){
 const mats=createStreetMaterials({...T,TextureLoader},{lite});
 assert.equal(urls.length,lite?8:4);
 for(const material of Object.values(mats)){
  assert.equal(material.map.colorSpace,T.SRGBColorSpace);
  assert.equal(material.normalMap.colorSpace,T.NoColorSpace);
  assert.equal(material.map.wrapS,T.RepeatWrapping);
  assert.equal(material.roughnessMap,null,'roughness packed in shared diffuse alpha');
  const shader={fragmentShader:T.ShaderLib.standard.fragmentShader};material.onBeforeCompile(shader);
  assert.ok(shader.fragmentShader.includes('roughnessFactor *= texture2D(map,vMapUv).a;'));
  assert.ok(T.ShaderChunk.map_fragment.includes('diffuseColor *= sampledDiffuseColor'),'Actual Three map chunk multiplies RGBA');
  assert.ok(shader.fragmentShader.includes('#include <map_fragment>\ndiffuseColor.a = opacity;'));
  assert.ok(shader.fragmentShader.indexOf('diffuseColor.a = opacity;')<shader.fragmentShader.indexOf('#include <opaque_fragment>'),'Reset occurs before intentional foreground fade');
 }
 assert.ok(urls.slice(-4).every(url=>url.endsWith((lite?512:1024)+'.webp')));
}
// Adjacent pavement slabs share world metric phase, avoiding seam/reset on each slab.
for(const centre of [[0,-.2,0],[0,-.08,7.25]]){
 const geo=new T.BoxGeometry(60,.1,3.1);streetMetricUv(geo,centre,1.8);
 const p=geo.attributes.position,n=geo.attributes.normal,uv=geo.attributes.uv;
 for(let i=0;i<p.count;i++)if(n.getY(i)>.9){assert.ok(Math.abs(uv.getX(i)-(p.getX(i)+centre[0])/1.8)<1e-5);assert.ok(Math.abs(uv.getY(i)-(p.getZ(i)+centre[2])/1.8)<1e-5);}
}
const manifest=JSON.parse(fs.readFileSync('web/house/assets/residential-street-pbr/manifest.json'));
assert.equal(manifest.license,'CC0 1.0');
for(const asset of manifest.assets)for(const output of asset.outputs){const bytes=fs.readFileSync('web/house/assets/residential-street-pbr/'+output.file);assert.equal(crypto.createHash('sha256').update(bytes).digest('hex'),output.sha256);}
console.log('PASS: four shared packed PBR textures, correct color/normal spaces, linear roughness alpha shader, full/lite quality, metre-scale continuous pavement UV and verified hashes');
