import assert from 'node:assert/strict';
import * as T from '../../web/house/vendor/three.module.js';
import {createHouseWindowView, facadeCoordinates, photographicIntersection} from '../../web/house/house_window_view.mjs';

// Texture creation does not need DOM/image downloads to check shader contracts.
class TextureLoader { load(){return new T.Texture();} }
const three={...T,TextureLoader};
const lower=createHouseWindowView(three,{base:'/room/window/'},'front');
const shared={};
for(const [name,uniform] of Object.entries({near:'tNear',mid:'tMid',mid_n:'tMidN',mid_l:'tMidL',far:'tFar',sky:'tSky',noise:'tNoise'}))
  shared[name]=lower.material.uniforms[uniform].value;
const upper=createHouseWindowView(three,{textures:shared},'front');
assert.equal(upper.material.uniforms.tMid.value,lower.material.uniforms.tMid.value,'panes share image GPU storage');
assert.deepEqual(upper.material.uniforms.uFacadeOrigin.value.toArray(),lower.material.uniforms.uFacadeOrigin.value.toArray());
assert.deepEqual(lower.material.uniforms.uGain.value.toArray(),[1,1]);
assert.deepEqual(lower.material.uniforms.uLift.value.toArray(),[0,0,0]);
assert.ok(lower.material.fragmentShader.includes('facadeDelta = vWorld - uFacadeOrigin'));
assert.ok(!lower.material.fragmentShader.includes('vec2 g = (vUv - 0.5) * uSize'));
assert.ok(!lower.material.fragmentShader.includes('slope = slope /'));
assert.ok(lower.material.fragmentShader.includes('uv.x <= 0.0 || uv.x >= 1.0'),'finite plates must not stretch repeated edge texels');

assert.equal(facadeCoordinates([-2,4.45,3.94],'front')[0],2);
assert.ok(Math.abs(facadeCoordinates([-2,4.45,3.94],'front')[1]-2.775)<1e-10);
assert.deepEqual(facadeCoordinates([3.25,1.675,3.94],'front'),[-3.25,0]);
assert.deepEqual(facadeCoordinates([-3.94,1.675,2],'west'),[-2,0]);
// Two eye heights looking at the same point on one outside plate have the
// same photo coordinates, rather than recentering an image on each floor.
const target=[-1,3,43.94];
for(const eye of [[0,1.65,0],[0,4.65,0]]) {
  const amount=3.94/43.94;
  const pane=eye.map((value,i)=>value+(target[i]-value)*amount);
  const hit=photographicIntersection(eye,pane,'front',40);
  assert.ok(Math.abs(hit[0]-1)<1e-10 && Math.abs(hit[1]-1.325)<1e-10);
}
const glass=[0,1.675,3.94];
assert.equal(photographicIntersection([0,1.675,0],glass,'front',40)[0],0);
assert.ok(photographicIntersection([1,1.675,0],glass,'front',40)[0]>10,'lateral eye movement produces physical parallax');
assert.throws(()=>createHouseWindowView(three,{},'unknown'),/Unknown house facade/);
console.log('PASS: shared texture/origin, floor-height horizon, coherent ray intersections, lateral parallax, no pane zoom or stretched photo edges');
