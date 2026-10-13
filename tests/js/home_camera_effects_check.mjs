import assert from 'node:assert/strict';
import * as T from '../../web/house/vendor/three.module.js';
import {createCameraEffects, adaptationBlend, CAMERA_DEFAULTS} from '../../web/house/camera_effects.mjs';
import {createSunShafts} from '../../web/house/sun_shafts.mjs';
const calls=[],targets=[];
let target=null;
const renderer={extensions:{has:()=>true},capabilities:{maxSamples:4},autoClear:true,
 getRenderTarget:()=>target,compileAsync:async(s,c)=>calls.push({compile:true,s,c,target}),
 getDrawingBufferSize:v=>v.set(1920,1080),
 setRenderTarget:t=>{target=t;targets.push(t);},
 render:(s,c)=>calls.push({s,c,target,material:s.children[0]?.material,autoClear:renderer.autoClear})};
const scene=new T.Scene(), camera=new T.PerspectiveCamera(64,16/9,.04,110);

const lite=createCameraEffects(T,renderer,true);
await lite.prepare(scene,camera);
assert.equal(lite.render(scene,camera,1/60),false);assert.equal(lite.target(),null);
assert.equal(calls.length,0);assert.equal(targets.length,0);
const noFloat=createCameraEffects(T,{...renderer,extensions:{has:()=>false}},false);
assert.equal(noFloat.render(scene,camera,1/60),false);assert.equal(calls.length,0);
console.log('PASS: lite and missing float targets bypass without allocation');

const fx=createCameraEffects(T,renderer,false);
assert.equal(fx.render(scene,camera,1/60),true);
const roomRenders=calls.filter(c=>c.s===scene);
assert.equal(roomRenders.length,1,'house rendered exactly once');
const input=roomRenders[0].target;
assert.ok(input.depthTexture===null||input.depthBuffer);assert.equal(input.samples,2);
assert.equal(input.texture.type,T.HalfFloatType);assert.equal(input.width,1920);
assert.equal(calls.at(-1).target,null,'final pass draws to the canvas');
assert.equal(target,null);
const levels=fx.stats().levels;assert.ok(levels>=4&&levels<=CAMERA_DEFAULTS.maxLevels);
const ups=calls.filter(c=>c.material?.blending===T.AdditiveBlending);
assert.equal(ups.length,levels-1);assert.ok(ups.every(c=>c.autoClear===false),'upsample accumulates without clearing');
assert.equal(renderer.autoClear,true,'autoClear restored');
assert.equal(calls.length,1+levels+(levels-1)+1+1);
console.log('PASS: one house render, bounded bloom chain, additive upsampling, meter and final canvas pass');

calls.length=0;
const shafts=createSunShafts(T,renderer,false), sun=new T.DirectionalLight();
camera.position.set(0,1.65,0);sun.position.set(-10,8,12);sun.castShadow=true;sun.shadow.map=new T.WebGLRenderTarget(8,8);
let shaftsActive=false;
assert.equal(fx.render(scene,camera,1/60,t=>(shaftsActive=shafts.render(scene,camera,{sunIntensity:2},sun,true,t))),true);
assert.ok(shaftsActive);
assert.equal(calls.filter(c=>c.s===scene).length,1,'shafts own the single house render');
const composite=calls[2];assert.equal(composite.target,fx.target(),'shaft composite writes the HDR camera input');
assert.equal(calls.at(-1).target,null);
console.log('PASS: sun shafts feed the camera chain without a second house render');

calls.length=0;
const sentinel=new T.WebGLRenderTarget(2,2);renderer.setRenderTarget(sentinel);
const warm=createCameraEffects(T,renderer,false);
await warm.prepare(scene,camera);
assert.ok(calls.every(c=>c.compile),'preparation compiles and never renders');
assert.equal(calls[0].s,scene);assert.equal(calls.at(-1).target,null);assert.equal(target,sentinel);
await shafts.prepare(scene,camera,warm.target());
assert.equal(calls.at(-1).target,warm.target(),'HDR composite variant prepared');assert.equal(target,sentinel);
renderer.setRenderTarget(null);
console.log('PASS: shader preparation restores the render target and covers the HDR shaft composite');

let disposed=0;
for(const t of fx.targets()) t.addEventListener('dispose',()=>disposed++);
const owned=fx.targets().length;fx.dispose();assert.equal(disposed,owned);assert.equal(fx.targets().length,0);
warm.dispose();shafts.dispose();sentinel.dispose();
console.log('PASS: every owned target disposed');

const a=adaptationBlend(1/30,.2,.5,1.6,.75), b=1-(1-adaptationBlend(1/60,.2,.5,1.6,.75))**2;
assert.ok(Math.abs(a-b)<1e-12,'30 and 60 fps adapt identically');
assert.ok(adaptationBlend(.1,.2,.5,1.6,.75)>adaptationBlend(.1,.5,.2,1.6,.75),'brightening adapts faster');
assert.equal(adaptationBlend(-1,.2,.5,1.6,.75),0);
console.log('PASS: frame-rate independent asymmetric eye adaptation');
