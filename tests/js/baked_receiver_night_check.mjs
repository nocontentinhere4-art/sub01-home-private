import assert from'node:assert/strict';
import fs from'node:fs';
import*as T from'../../web/house/vendor/three.module.js';
import{homeLighting}from'../../web/house/lighting.mjs';
import{configureBakedReceiverLighting,bakedReceiverChunks}from'../../web/house/baked_receiver_lighting.mjs';
const source=fs.readFileSync(new URL('../../web/house/home.js',import.meta.url),'utf8');
const begin=source.indexOf('function lighting(timestamp ='),end=source.indexOf('\nfunction shade()',begin);
assert.ok(begin>0&&end>begin);
const material=new T.MeshStandardMaterial();material.lightMap=new T.Texture();
const nightMap={value:new T.Texture()},nightIntensity={value:0};
configureBakedReceiverLighting(T,material,{occludedDayReady:true,nightLightMap:nightMap,nightLightIntensity:nightIntensity});
const glow=new T.MeshStandardMaterial();glow.userData.lampEmission=1.3;
const scene=new T.Scene();scene.background=new T.Color();scene.fog=new T.Fog(0,1,10);
const datasets={};
const state={homeLighting,visualLightTime:t=>t,currentLight:null,lastLightMinute:0,sun:new T.DirectionalLight(),lite:false,
 sunlightShadowFitReady:false,fitSunlightShadow:()=>{throw new Error('Night sun must remain disabled');},hemi:new T.HemisphereLight(),scene,
 indirectMaterials:[material],nightLightIntensity:nightIntensity,lampOn:true,warm:new T.PointLight(),bedLight:new T.PointLight(),
 kitchenWorkLight:new T.PointLight(),ceilingLights:[new T.SpotLight()],switchedMaterials:new Set([glow]),glowMat:glow,
 renderer:{shadowMap:{needsUpdate:false}},document:{getElementById:()=>({dataset:datasets})}};
// Execute the actual house night lighting function, not a parallel hand-written
// setup: this verifies the live practical-light path alongside the new hook.
const apply=new Function('state','timestamp',`with(state){${source.slice(begin,end)};lighting(timestamp);}`);
const nightTimestamp=(23-9)*3600;
apply(state,nightTimestamp);
assert.equal(state.currentLight.hour,23);assert.equal(state.currentLight.daylight,0);assert.equal(state.sun.intensity,0);assert.equal(state.sun.castShadow,false);
assert.equal(material.lightMapIntensity,0,'No daytime sky/lightmap enters an actual night receiver');
assert.equal(nightIntensity.value,Math.PI,'Validated night indirect radiance still converts to irradiance');
assert.equal(state.warm.intensity,12);assert.equal(state.bedLight.intensity,3.5);assert.equal(state.kitchenWorkLight.intensity,2.4);assert.equal(state.ceilingLights[0].intensity,10);
assert.equal(glow.emissiveIntensity,1.3,'Live fixture emission retains real lamp state');
const shader={fragmentShader:T.ShaderLib.standard.fragmentShader,uniforms:{}};material.onBeforeCompile(shader);
assert.equal(shader.uniforms.homeNightLightMap,nightMap);assert.equal(shader.uniforms.homeNightLightIntensity,nightIntensity);
const chunks=bakedReceiverChunks(T);
assert.ok(chunks.begin.includes('getPointLightInfo( pointLight, geometryPosition, directLight );'));
assert.ok(chunks.begin.includes('getSpotLightInfo( spotLight, geometryPosition, directLight );'));
assert.ok(chunks.begin.includes('getPointShadow('));assert.ok(chunks.begin.includes('getShadow('));
assert.ok(shader.fragmentShader.includes('#include <lights_fragment_end>'),'Night indirect BRDF still accumulates');
state.lampOn=false;apply(state,nightTimestamp);
assert.equal(nightIntensity.value,0);for(const light of[state.warm,state.bedLight,state.kitchenWorkLight,...state.ceilingLights])assert.equal(light.intensity,0);
assert.equal(glow.emissiveIntensity,0);assert.equal(material.lightMapIntensity,0);
const recipe=fs.readFileSync(new URL('../../tools/bake_home_indirect.py',import.meta.url),'utf8');
assert.ok(recipe.includes('0.12 if mode == "day" else 0'),'Actual existing night bake has no world-light source');
console.log('PASS actual home lighting function atTokyo23: daymap/sky contribution zero; nightmap PI on/off retained; actual desk/bed/kitchen/pendant direct intensities and emission retained; point/spot shadow shader paths unchanged; actual night bake world=0');
