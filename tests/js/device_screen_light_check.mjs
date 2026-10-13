import assert from 'node:assert/strict';
import * as T from '../../web/house/vendor/three.module.js';
import {createDeviceScreenLight} from '../../web/house/device_screen_light.mjs';
const close=(actual,expected)=>assert.ok(Math.abs(actual-expected)<1e-7,`${actual} != ${expected}`);
function fixture(){
 const scene=new T.Scene(),texture=new T.Texture(),geometry=new T.PlaneGeometry(),material=new T.MeshBasicMaterial({map:texture}),screen=new T.Mesh(geometry,material);scene.add(screen);
 const device={width:640,height:360},tiny={width:0,height:0};let samples=0,fail=false,rgba=[255,255,255,255],resourceDisposals=0;
 for(const resource of[texture,geometry,material])resource.addEventListener('dispose',()=>resourceDisposals++);
 tiny.getContext=()=>({clearRect(){},drawImage(input){assert.equal(input,device);samples++;if(fail)throw new Error('SecurityError');},getImageData(){return{data:rgba};}});
 const control=createDeviceScreenLight(T,scene,screen,{maxIntensity:2,distance:2.7,createCanvas:()=>tiny});
 return{scene,screen,texture,geometry,material,device,tiny,control,get samples(){return samples;},get resourceDisposals(){return resourceDisposals;},set fail(value){fail=value;},set rgba(value){rgba=value;}};
}
const f=fixture();assert.equal(f.tiny.width,1);assert.equal(f.tiny.height,1);assert.equal(f.control.light.castShadow,false);assert.equal(f.control.light.userData.excludeStaticBake,true);assert.equal(f.control.target.userData.excludeStaticBake,true);
f.control.update(.1,f.device);assert.equal(f.samples,1);assert.ok(f.control.light.intensity>0&&f.control.light.intensity<2);assert.equal(f.control.light.distance,2.7);
for(let i=0;i<4;i++)f.control.update(.1,f.device);assert.equal(f.samples,1,'one immediate sample and no resample before 0.5s');f.control.update(.1,f.device);assert.equal(f.samples,2);
let direction=new T.Vector3().subVectors(f.control.target.position,f.control.light.position).normalize();close(direction.z,1);close(direction.x,0);
f.screen.rotation.y=Math.PI/2;f.control.update(.1,f.device);direction.subVectors(f.control.target.position,f.control.light.position).normalize();close(direction.x,1);close(direction.z,0);
f.screen.rotation.set(-Math.PI/2,0,0);f.control.update(.1,f.device);direction.subVectors(f.control.target.position,f.control.light.position).normalize();close(direction.y,1);close(direction.z,0);
// A camera child includes its full parent transform, without moving the camera.
const camera=new T.PerspectiveCamera();camera.position.set(7,2,-4);camera.rotation.y=Math.PI/3;f.scene.add(camera);camera.add(f.screen);f.screen.position.set(.1,-.2,-.5);f.screen.rotation.set(0,0,0);const cameraBefore=camera.matrix.clone();
f.control.update(.1,f.device);const expected=new T.Vector3(0,0,1).applyQuaternion(camera.quaternion);direction.subVectors(f.control.target.position,f.control.light.position).normalize();close(direction.x,expected.x);close(direction.z,expected.z);assert.equal(camera.matrix.equals(cameraBefore),false,'normal scene matrix update is allowed');const cameraPosition=camera.position.clone();f.control.update(.1,f.device);assert.equal(camera.position.equals(cameraPosition),true);
for(const flags of[{active:false},{privacy:true},{hidden:true}]){const samples=f.samples;f.control.update(.1,f.device,flags);assert.equal(f.control.light.intensity,0);assert.equal(f.samples,samples,'private/inactive frames cannot be sampled');}
// Measured sRGB becomes linear brightness; pure mid-grey is ~0.216 of white.
f.rgba=[128,128,128,255];for(let i=0;i<40;i++)f.control.update(.1,f.device);const linearGrey=Math.pow((128/255+.055)/1.055,2.4);assert.ok(Math.abs(f.control.light.intensity-2*linearGrey)<1e-6);
f.rgba=[0,0,255,255];for(let i=0;i<40;i++)f.control.update(.1,f.device);assert.ok(Math.abs(f.control.light.intensity-2*.0722)<1e-6);assert.ok(f.control.light.color.b>.999);
f.fail=true;for(let i=0;i<40;i++)f.control.update(.1,f.device);assert.ok(f.control.light.intensity<1e-6,'failed reads fade the stale glow off');f.fail=false;f.rgba=[255,255,255,255];f.control.update(1000,f.device);assert.ok(f.control.light.intensity<1,'large frame gap cannot jump immediately to max intensity');
f.control.dispose();f.control.dispose();assert.equal(f.control.light.parent,null);assert.equal(f.control.target.parent,null);assert.equal(f.resourceDisposals,0);assert.equal(f.device.width,640);assert.equal(f.tiny.width,0);const samples=f.samples;f.control.update(1,f.device);assert.equal(f.samples,samples);
const toggled=fixture();toggled.control.update(.01,toggled.device);for(let i=0;i<10;i++){toggled.control.update(.01,toggled.device,{active:false});toggled.control.update(.01,toggled.device);}assert.equal(toggled.samples,1,'rapid activation changes cannot bypass the sampling rate cap');toggled.control.dispose();
const noCanvas=createDeviceScreenLight(T,new T.Scene(),new T.Mesh(new T.PlaneGeometry(),new T.MeshBasicMaterial()),{createCanvas(){throw new Error('No canvas');}});noCanvas.update(1,{width:10,height:10});assert.equal(noCanvas.light.intensity,0);noCanvas.dispose();
assert.throws(()=>createDeviceScreenLight(T,new T.Scene(),f.screen,{sampleInterval:.1}),/2 Hz/);
console.log('PASS: real PC/rotated-TV/phone and camera-parent normals; 1×1 measured sRGB→linear intensity/color; <=2 Hz sampling; bounded fade; immediate inactive/privacy/hidden off with no sampling; failed canvas safely fades; owned light/target excluded from static bake; shared screen resources/camera/device canvas preserved.');
