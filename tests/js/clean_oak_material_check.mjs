import assert from 'node:assert/strict';
import * as T from 'three';
import {createCleanKitchenOak,cleanKitchenBoxUv,CLEAN_OAK_MATCH} from '../../web/house/clean_oak_material.mjs';
const source=new T.MeshStandardMaterial({map:new T.Texture(),normalMap:new T.Texture(),roughnessMap:new T.Texture(),roughness:.92});source.normalScale.set(.1,.1);
const material=createCleanKitchenOak(T,source);
assert.equal(material.map,source.map);assert.equal(material.normalMap,source.normalMap);assert.equal(material.roughnessMap,source.roughnessMap);
assert.equal(material.userData.lightOak,false);assert.equal(material.roughness,.92);assert.equal(material.normalScale.x,.1);
for(let i=0;i<3;i++)assert(Math.abs(material.color.toArray()[i]*CLEAN_OAK_MATCH.oakLinearMean[i]-CLEAN_OAK_MATCH.previousLinearMean[i])<1e-8);
const door=new T.BoxGeometry(.65,.76,.035),before=Array.from(door.attributes.position.array);
cleanKitchenBoxUv(door,[-1.9,.44,-3.215]);
const p=door.attributes.position,n=door.attributes.normal,uv=door.attributes.uv;
for(let i=0;i<p.count;i++)if(n.getZ(i)>.9){assert(Math.abs(uv.getX(i)-(p.getX(i)-1.9)/1.83)<1e-6);assert(Math.abs(uv.getY(i)-(p.getY(i)+.44)/1.83)<1e-6,'cabinet-front grain follows vertical V at real1.83m scan density');}
assert.deepEqual(Array.from(door.attributes.position.array),before);
assert.equal(source.color.getHexString(),'ffffff');
console.log('PASS: licensed/shared clean oak maps, unchanged source material, matched full-scan linear albedo, no second bleachgrade, physical cabinet-front vertical grain and identical positions.');
