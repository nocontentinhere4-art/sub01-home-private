import assert from 'node:assert/strict';
import * as T from 'three';
import {FURNISHING_DETAIL as D,applyQueenBedOak,applyHavenSeamDetail,restoreRugScannedRoughness} from '../../web/house/furnishing_detail.mjs';
import {createWovenRugMaterial} from '../../web/house/woven_rug_material.mjs';
import {createHavenSofaMaterials} from '../../web/house/haven_sofa_materials.mjs';

const textures=()=>({map:new T.Texture(),normalMap:new T.Texture(),roughnessMap:new T.Texture()});
const before=new T.Texture().id;

// 1. Queen bed oak: shared texture objects, metric 1.83 m density, no vertex change.
const oak=new T.MeshStandardMaterial({...textures(),roughness:.92});oak.normalScale.set(.10,.10);
const source=new T.MeshStandardMaterial({name:'Original oak grain',map:new T.Texture(),roughness:.5});
const bed=new T.BoxGeometry(1.54,.025,1.897);bed.setAttribute('uv1',bed.attributes.uv.clone());
// Give the box the source convention: 1 UV unit per metre.
const p=bed.attributes.position,n=bed.attributes.normal,uv=bed.attributes.uv;
for(let i=0;i<p.count;i++)uv.setXY(i,Math.abs(n.getY(i))>.9?p.getX(i):p.getZ(i),Math.abs(n.getY(i))>.9?p.getZ(i):p.getY(i));
const positions=Array.from(p.array),uv1=Array.from(bed.attributes.uv1.array),uv0=Array.from(uv.array);
const material=applyQueenBedOak(source.clone(),bed,oak,'full');
assert.equal(material.map,oak.map);assert.equal(material.normalMap,oak.normalMap);assert.equal(material.roughnessMap,oak.roughnessMap);
assert.equal(material.normalScale.x,.10);assert.equal(material.roughness,D.queenBedOak.roughnessFactor.full);
assert.equal(material.color.getHexString(),new T.Color(D.queenBedOak.color).getHexString(),'same graded colour as before');
for(let i=0;i<uv.count*2;i++)assert(Math.abs(uv.array[i]-uv0[i]/1.83)<1e-6,'1.83 m per oak tile');
assert.deepEqual(Array.from(p.array),positions,'geometry unchanged');
assert.deepEqual(Array.from(bed.attributes.uv1.array),uv1,'baked-light uv1 unchanged');
applyQueenBedOak(source.clone(),bed,oak,'lite');
for(let i=0;i<uv.count*2;i++)assert(Math.abs(uv.array[i]-uv0[i]/1.83)<1e-6,'idempotent UV scale');
assert.equal(applyQueenBedOak(source.clone(),new T.BoxGeometry(),oak,'lite').roughness,D.queenBedOak.roughnessFactor.lite);
assert.throws(()=>applyQueenBedOak(source.clone(),bed,{map:oak.map}),/shared architecture oak/);
assert.throws(()=>applyQueenBedOak(source.clone(),bed,oak,'4k'),/tier/);

// 2. Haven seams reuse the panel linen textures; the owner's loader still loads six maps.
const urls=[];
const haven=createHavenSofaMaterials(T,{load(url){urls.push(url);return new T.Texture();}},'/house/assets/',8);
const seamColor=haven.Haven_seams.color.getHexString();
applyHavenSeamDetail(haven,'full');
assert.equal(urls.length,6,'no extra bitmap requested');
assert.equal(haven.Haven_seams.normalMap,haven.Haven_linen.normalMap);
assert.equal(haven.Haven_seams.roughnessMap,haven.Haven_linen.roughnessMap);
assert.equal(haven.Haven_seams.normalScale.x,haven.Haven_linen.normalScale.x);
assert.equal(haven.Haven_seams.map,null,'licensed flat flax albedo retained');
assert.equal(haven.Haven_seams.color.getHexString(),seamColor);
assert.equal(haven.Haven_seams.roughness,D.havenSeams.roughnessFactor.full);
assert.equal(haven.Haven_felt.normalMap,null,'hidden underside felt left flat');

// 3. Rug: default helper behaviour unchanged; opt-in restores the shared map.
const linen=new T.MeshStandardMaterial(textures());
const rug=createWovenRugMaterial(T,linen,'#c4b49a');
assert.equal(rug.roughnessMap,null);assert.equal(rug.roughness,.98);
restoreRugScannedRoughness(rug,linen,'lite');
assert.equal(rug.roughnessMap,linen.roughnessMap);assert.equal(rug.map,linen.map);
assert.equal(rug.roughness,D.wovenRug.roughnessFactor.lite);
assert.throws(()=>restoreRugScannedRoughness(rug,{}),/linen roughness/);

// oak 3 + source map 1 + Haven loader 6 + linen 3 + this probe 1: helpers create no Texture.
assert.equal(new T.Texture().id-before,14,'helpers never clone or create textures');
console.log('PASS: bed oak/sofa seams/rug reuse existing texture objects, preserve previous mean roughness factors, 1.83 m oak density, unchanged positions and uv1, opt-in rug map.');
