import assert from 'node:assert/strict';
import * as T from '../../web/house/vendor/three.module.js';
import {createSunShafts} from '../../web/house/sun_shafts.mjs';
const calls=[],targets=[];
let target=null;
const renderer={extensions:{has:()=>true},capabilities:{maxSamples:2},
 getDrawingBufferSize: v=>v.set(1920,1080),
 setRenderTarget: t=>{target=t;targets.push(t);},render:(s,c)=>calls.push({s,c,target})};
const scene=new T.Scene(), camera=new T.PerspectiveCamera(64,16/9,.04,110), sun=new T.DirectionalLight();
camera.position.set(0,1.65,0);sun.position.set(-10,8,12);sun.castShadow=true;
sun.shadow.map=new T.WebGLRenderTarget(8,8);
const light={sunIntensity:2};
const lite=createSunShafts(T,renderer,true);
assert.equal(lite.render(scene,camera,light,sun,true),false);assert.equal(lite.pixels(),0);
const effect=createSunShafts(T,renderer,false);
assert.equal(effect.render(scene,camera,light,sun,false),false);assert.equal(effect.pixels(),0);
assert.equal(effect.render(scene,camera,{sunIntensity:0},sun,true),false);assert.equal(effect.pixels(),0);
assert.equal(effect.render(scene,camera,light,sun,true),true);
assert.equal(calls.length,3);assert.equal(calls.filter(c=>c.s===scene).length,1);
assert.equal(target,null);assert.ok(effect.pixels()<=240000);
assert.equal(calls[0].target.samples,2);assert.ok(calls[0].target.depthTexture);
assert.notEqual(calls[0].target,calls[1].target);
let disposed=0;
for(const t of targets.filter(Boolean)) t.addEventListener('dispose',()=>disposed++);
effect.dispose();assert.equal(disposed,2);
console.log('PASS: zero lite/dark/closed-curtain allocation, one house render, bounded volume, depth target, MSAA and target disposal');
