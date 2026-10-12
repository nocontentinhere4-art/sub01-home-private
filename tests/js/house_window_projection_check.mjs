import assert from 'node:assert/strict';
import * as T from '../../web/house/vendor/three.module.js';
import {createHouseWindowView,doorGlassCoverage} from '../../web/house/house_window_view.mjs';
let downloads=0;class TextureLoader{load(){downloads++;return new T.Texture();}}
const three={...T,TextureLoader};
const scene=new T.Scene(),door={value:0};
const lower=createHouseWindowView(three,{},'front');
const upper=createHouseWindowView(three,{doorOpenness:door},'front');
for(const view of [lower,upper]){
 view.build({c:[0,2,3.94],w:3,h:2,ry:Math.PI},scene);
 assert.equal(view.material.transparent,true);assert.equal(view.material.depthWrite,false);
 assert.equal(view.material.side,T.DoubleSide);assert.equal(view.state().textures,0);
 assert.equal(view.mesh.userData.excludeStaticBake,true,'glass should not become opaque indoor GI');
 assert.ok(!view.material.fragmentShader.includes('sampler2D'),'no per-pane picture copies');
}
assert.equal(downloads,0);assert.equal(upper.material.uniforms.uDoorOpenness,door);
assert.equal(lower.material.uniforms.uDoorReveal.value,0);assert.equal(upper.material.uniforms.uDoorReveal.value,1);
assert.equal(doorGlassCoverage(-2.2,4.65,0),1);assert.equal(doorGlassCoverage(-2.2,4.65,.25),1);
assert.equal(doorGlassCoverage(-2.2,4.65,1),0);assert.equal(doorGlassCoverage(-3.5,4.65,1),1);
assert.ok(upper.material.fragmentShader.includes('discard;'),'cleared doorway has no glass overlay');
assert.throws(()=>createHouseWindowView(three,{},'unknown'),/Unknown house facade/);
console.log('PASS: physical double-sided transparent glass, no photograph/image storage, cleared sliding doorway and fixed sidelight masking');
