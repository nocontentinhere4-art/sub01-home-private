import assert from 'node:assert/strict';
import fs from 'node:fs';
import * as T from '../../web/house/vendor/three.module.js';
import {createDeviceScreenLight} from '../../web/house/device_screen_light.mjs';
import {staticBakeScene} from '../../web/house/balcony_access.mjs';
const source=fs.readFileSync(new URL('../../web/house/home.js',import.meta.url),'utf8');
const section=(start,end)=>{const a=source.indexOf(start),b=source.indexOf(end,a);assert.ok(a>=0&&b>a,`Missing actual source ${start}`);return source.slice(a,b);};
const computer=section('const screenCanvas = document.createElement("canvas");','\ninteractions.push({\n  object: screen,');
const television=section('const tv = new T.Mesh(', '\ninteractions.push({\n  object: tv,');
const phone=section('const phoneDisplay = new T.Mesh(', '\n// Screen, speaker and buttons');
const update=section('const deviceScreenLights = [];','\nfunction invalidateDeviceBitmaps()');
const initialize=section('for (const [name, mesh, canvas, maxIntensity, distance] of [','\ninteractions.push({\n  object: phoneMesh,');
const privacy=section('function setPrivacy(active) {','\nfunction browserFrame(');
const visibility=section("document.addEventListener('visibilitychange',",'\nfunction notice(text)');
const framePrefix=section('renderer.setAnimationLoop(() => {',"\n  document.getElementById('status').dataset.exterior =")+'\n});';
const draws=[],canvases=[],events=new Map(),scene=new T.Scene();
function canvas(){const c={width:0,height:0,pixel:[255,255,255,255]};const ctx={canvas:c,clearRect(){},drawImage(input){draws.push(input);this.input=input;},getImageData(){return{data:this.input.pixel};}};c.getContext=()=>ctx;canvases.push(c);return c;}
const tvCanvas=canvas(),phoneCanvas=canvas();tvCanvas.width=800;tvCanvas.height=460;phoneCanvas.width=256;phoneCanvas.height=512;
const scope={T,scene,tvCanvas,phoneCanvas,tvTexture:new T.CanvasTexture(tvCanvas),phoneTexture:new T.CanvasTexture(phoneCanvas),
 document:{hidden:false,createElement:()=>canvas(),addEventListener:(name,fn)=>events.set(name,fn),body:{classList:{toggle(){}}}},
 homeState:{activity:'sleep',privacy:false},privacyActive:false,keys:{},drag:false,visitorMotion:{reset(){}},lite:false,
 renderer:{shadowMap:{},info:{reset(){}},setAnimationLoop(fn){this.loop=fn;}},
 closePanel(){},invalidateDeviceBitmaps(){},phoneMusicFeed:{stop(){}},browserControls:new Map(),panelKind:'',phoneApp:'home',renderPanel(){},refreshPanelScreens(){},
 accumulated:0,clock:{getDelta:()=>.05},curtainPanels:[],startup:{ready:false},update(){},
 createDeviceScreenLight:(...args)=>createDeviceScreenLight(...args.slice(0,3),{...args[3],createCanvas:()=>canvas()}),
};
// Use actual initializers and actual privacy/visibility handlers, not copied gates.
const controls=new Function('scope',`with(scope){${computer}\n${update}\n${privacy}\n${visibility}\n${television}\n${phone}\n${initialize}\n${framePrefix}\nreturn{deviceScreenLights,updateDeviceScreenLights,setPrivacy,screen,tv,phoneDisplay};}`)(scope);
assert.deepEqual(controls.deviceScreenLights.map(x=>x.name),['computer','television','phone']);assert.equal(draws.length,0,'constructing controllers before render does not sample');
for(const [device,mesh,distance] of [[controls.deviceScreenLights[0],controls.screen,1.8],[controls.deviceScreenLights[1],controls.tv,2.7],[controls.deviceScreenLights[2],controls.phoneDisplay,.6]]){
 assert.equal(device.canvas,mesh.material.map.image,'actual constructor binds the material-owned canvas, not a separate screenshot');assert.equal(device.controller.light.distance,distance);assert.equal(device.controller.light.castShadow,false);
}
scope.renderer.loop();assert.equal(draws.length,0,'startup gate blocks sampling before materials are ready');
scope.startup.ready=true;scope.renderer.loop();assert.equal(draws.length,3);assert.deepEqual(new Set(draws),new Set(controls.deviceScreenLights.map(x=>x.canvas)));
for(const [i,axis]of [[0,new T.Vector3(0,0,1)],[1,new T.Vector3(1,0,0)],[2,new T.Vector3(0,1,0)]]){const c=controls.deviceScreenLights[i].controller;assert.ok(new T.Vector3().subVectors(c.target.position,c.light.position).normalize().distanceTo(axis)<1e-8,'actual display transform directs its light away from its screen');}
// Paused/sleeping devices retain their real cached screen glow: no device actions.
for(let i=0;i<120;i++)scope.renderer.loop();for(const [i,cap]of [[0,.7],[1,2],[2,.03]])assert.ok(Math.abs(controls.deviceScreenLights[i].controller.light.intensity-cap)<1e-8);
let before=draws.length;controls.setPrivacy(true);assert.equal(draws.length,before);for(const d of controls.deviceScreenLights)assert.equal(d.controller.light.intensity,0);
scope.renderer.loop();assert.equal(draws.length,before,'actual render function cannot sample in bathroom privacy');
scope.homeState.privacy=true;controls.setPrivacy(false);for(let i=0;i<20;i++)scope.renderer.loop();assert.equal(draws.length,before,'server home privacy protects the same real canvases');scope.homeState.privacy=false;
for(let i=0;i<20;i++)scope.renderer.loop();assert.ok(controls.deviceScreenLights[0].controller.light.intensity>0);
before=draws.length;scope.document.hidden=true;events.get('visibilitychange')();for(const d of controls.deviceScreenLights)assert.equal(d.controller.light.intensity,0);scope.renderer.loop();assert.equal(draws.length,before,'visibility handler zeroes immediately before hidden RAF stops');
scope.document.hidden=false;events.get('visibilitychange')();for(let i=0;i<20;i++)scope.renderer.loop();assert.ok(draws.length>before);
// Real staticBakeScene strips both emitters and targets, preserving source scene.
const sourceObjects=new Set();scene.traverse(o=>sourceObjects.add(o));const baked=staticBakeScene(scene);let spots=0,excluded=0;baked.traverse(o=>{if(o.isSpotLight)spots++;if(o.userData.excludeStaticBake)excluded++;});assert.equal(spots,0);assert.equal(excluded,0);
for(const device of controls.deviceScreenLights){assert.ok(sourceObjects.has(device.controller.light));assert.equal(device.controller.light.parent,scene);assert.equal(device.controller.target.parent,scene);}
assert.ok(baked.children.some(o=>o.isMesh),'real display geometry survives static export');
for(const device of controls.deviceScreenLights)device.controller.dispose();assert.equal(scene.children.includes(controls.screen),true);assert.equal(controls.screen.material.map.image.width,1024);
assert.ok(source.indexOf('const deviceScreenLights = [];')<source.indexOf("document.addEventListener('visibilitychange',"));assert.ok(source.indexOf('for (const [name, mesh, canvas, maxIntensity, distance] of [')<source.indexOf('renderer.setAnimationLoop(() => {'),'real initialization completes before the rendering loop is installed');
assert.ok(source.indexOf('for (const [name, mesh, canvas, maxIntensity, distance] of [')<source.indexOf('startup.prepare(renderer, scene,'),'all actual lights exist before shader preparation, not cold-added after readiness');
console.log('PASS actual home.js screen-light integration: material-owned desktop/TV/phone canvases; initialization and startup gates; cached sleeping-device glow; immediate bathroom/home privacy and hidden zero/no sampling; real bake strips lights+targets without touching source displays; <=existing caps and private-only source lifecycle.');
