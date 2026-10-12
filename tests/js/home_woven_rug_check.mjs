import assert from 'node:assert/strict';
import * as T from '../../web/house/vendor/three.module.js';
import {createWovenRugMaterial,alignRugTextureUv,createWovenRugGeometries,WOVEN_RUG_SOURCE as stats} from '../../web/house/woven_rug_material.mjs';
import {RoundedBoxGeometry} from '../../web/house/vendor/RoundedBoxGeometry.js';
import {mergeGeometries} from '../../web/house/vendor/BufferGeometryUtils.js';
const source=new T.MeshStandardMaterial({map:new T.Texture(),normalMap:new T.Texture(),roughnessMap:new T.Texture()});
source.map.repeat.set(2,2);source.normalMap.repeat.set(2,2);
for(const color of ['#c4b49a','#a2aa9d','#d3c4a9']){
 const previous=new T.Color(color),material=createWovenRugMaterial(T,source,color);
 assert.equal(material.map,source.map);assert.equal(material.normalMap,source.normalMap);
 assert.equal(material.roughnessMap,null);assert.equal(material.roughness,.98);assert.equal(material.metalness,0);
 assert.equal(material.normalScale.x,.65);assert.equal(material.normalScale.y,.65);
 for(let c=0;c<3;c++){
  const old=previous.toArray()[c]*stats.oldLinearMean[c],now=material.color.toArray()[c]*stats.linenLinearMean[c];
  assert(Math.abs(now-old)<1e-8,'existing rug mean linear reflectance preserved');
  assert(material.color.toArray()[c]<=1,'exportable legal PBR base color factor');
 }
 material.dispose();
}
assert.equal(source.roughnessMap.isTexture,true);assert.equal(source.normalScale.x,1,'shared linen material not mutated');
const geometry=new T.BoxGeometry(3,.018,3.3),before=Array.from(geometry.attributes.position.array);
geometry.setAttribute('uv1',geometry.attributes.uv.clone());const uv1=Array.from(geometry.attributes.uv1.array);
alignRugTextureUv(geometry,[-2.4,.021,.1],[-2.4,0,.1]);
assert.deepEqual(Array.from(geometry.attributes.position.array),before,'no GI shape/bounds change');
assert.deepEqual(Array.from(geometry.attributes.uv1.array),uv1,'existing baked lightmap UV unchanged');
const stripe=new T.BoxGeometry(2.92,.003,.012), stripeCentre=[-2.4,.034,.1-3.3/2+.08];
alignRugTextureUv(stripe,stripeCentre,[-2.4,0,.1]);
const normals=stripe.attributes.normal,positions=stripe.attributes.position,uv=stripe.attributes.uv;
for(let i=0;i<positions.count;i++)if(normals.getY(i)>.9){
 assert(Math.abs(uv.getX(i)-positions.getX(i)/(2/3))<1e-6);
 assert(Math.abs(uv.getY(i)-(positions.getZ(i)+stripeCentre[2]-.1)/(2/3))<1e-6,'stripe samples same world-aligned textile as rug body');
}
assert.equal(stats.effectiveMapCoverageMetres,1/3);
for(const [width,depth] of [[3,3.3],[2.7,2.3],[2.65,3]]){
 const rug=createWovenRugGeometries(RoundedBoxGeometry,mergeGeometries,width,depth);
 assert(Math.abs(rug.body.boundingBox.max.x-rug.body.boundingBox.min.x-width)<1e-5);
 assert(Math.abs(rug.body.boundingBox.max.z-rug.body.boundingBox.min.z-depth)<1e-5);
 assert(Math.abs(rug.body.boundingBox.max.y-rug.body.boundingBox.min.y-.018)<1e-6,'unchanged cloth body thickness');
 const p=rug.hem.attributes.position;
 for(let i=0;i<p.count;i++){
  assert(Math.abs(p.getX(i))<=width/2&&Math.abs(p.getZ(i))<=depth/2,'hem stays in original footprint');
  assert(width/2-Math.abs(p.getX(i))<.04||depth/2-Math.abs(p.getZ(i))<.04,'no stripe crosses the rug interior');
  assert(p.getY(i)<.015,'subtle raised sewing, not floorboard depth');
 }
 assert.equal(rug.hem.groups.length,0,'one joined perimeter draw, no extra stripe materials');
 rug.body.dispose();rug.hem.dispose();
}
console.log('PASS: shared woven maps, matched base reflectance, continuous UV, unchanged body footprint/thickness and joined perimeter-only hem with no interior bars.');
