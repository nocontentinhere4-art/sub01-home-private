import assert from 'node:assert/strict';
import * as T from '../../web/house/vendor/three.module.js';
import {GLTFExporter} from '../../web/house/vendor/GLTFExporter.js';
import {staticBakeScene} from '../../web/house/balcony_access.mjs';
globalThis.FileReader=class{readAsArrayBuffer(blob){blob.arrayBuffer().then(b=>{this.result=b;this.onloadend?.();});}};
const scene=new T.Scene(),parent=new T.Group(),targets=new T.Group();
parent.position.set(1,2,-3);parent.rotation.set(.2,.4,-.1);parent.scale.set(1.3,.8,1.6);scene.add(parent);
targets.position.set(-2,.5,4);targets.rotation.set(.1,-.6,.15);scene.add(targets);
const sun=new T.DirectionalLight(0xffffff,2.2627416998);sun.name='fixture-sun';sun.position.set(-9,10,8);parent.add(sun);
const spot=new T.SpotLight(0xffffff,10);spot.name='fixture-spot';spot.position.set(2,3,-1);parent.add(spot);
for(const [light,p]of[[sun,[.2,1,-2]],[spot,[1,-.4,-3]]]){light.target.position.set(...p);targets.add(light.target);}
const point=new T.PointLight(0xffffff,12);point.name='fixture-point';point.position.set(1,2,3);parent.add(point);
const mesh=new T.Mesh(new T.BoxGeometry(1,1,1),new T.MeshStandardMaterial());mesh.name='unchanged-mesh';mesh.userData.bakeId='unchanged';parent.add(mesh);
const vertical=new T.SpotLight(0xffffff,10);vertical.name='fixture-vertical-spot';vertical.position.set(2,2.43,.5);vertical.target.position.set(2,0,.5);scene.add(vertical,vertical.target);
scene.updateMatrixWorld(true);
const snapshot=l=>({position:l.position.toArray(),quaternion:l.quaternion.toArray(),scale:l.scale.toArray(),target:l.target?.position.toArray(),targetParent:l.target?.parent?.uuid});
const before=[sun,spot,point,vertical].map(snapshot);const desired=[sun,spot,vertical].map(l=>l.target.getWorldPosition(new T.Vector3()).sub(l.getWorldPosition(new T.Vector3())).normalize());
const copy=staticBakeScene(scene);assert.deepEqual([sun,spot,point,vertical].map(snapshot),before,'live light transforms/targets are immutable');
assert.deepEqual(copy.getObjectByName('unchanged-mesh').geometry.attributes.position.array,mesh.geometry.attributes.position.array,'no receiver geometry changes');
for(const l of [sun,spot,vertical]){const c=copy.getObjectByName(l.name);assert.equal(c.target.parent,c);assert.deepEqual(c.target.position.toArray(),[0,0,-1]);}
const bin=await new GLTFExporter().parseAsync(copy,{binary:true,onlyVisible:true});const bytes=new Uint8Array(bin);const view=new DataView(bin);const json=JSON.parse(new TextDecoder().decode(bytes.slice(20,20+view.getUint32(12,true))));
const worlds=new Map();function walk(i,parent=new T.Matrix4()){const n=json.nodes[i],local=n.matrix?new T.Matrix4().fromArray(n.matrix):new T.Matrix4().compose(new T.Vector3().fromArray(n.translation||[0,0,0]),new T.Quaternion().fromArray(n.rotation||[0,0,0,1]),new T.Vector3().fromArray(n.scale||[1,1,1]));const world=parent.clone().multiply(local);worlds.set(i,world);for(const child of n.children||[])walk(child,world);}for(const i of json.scenes[json.scene||0].nodes)walk(i);
for(let k=0;k<3;k++){const i=json.nodes.findIndex(n=>n.name===[sun.name,spot.name,vertical.name][k]);const actual=new T.Vector3(0,0,-1).transformDirection(worlds.get(i));assert.ok(actual.angleTo(desired[k])<1e-7,'actual glTF world light axis must match original world target, with rotated/nonuniform parents');const ext=json.nodes[i].extensions.KHR_lights_punctual;assert.equal(json.extensions.KHR_lights_punctual.lights[ext.light].intensity,[sun.intensity,spot.intensity,vertical.intensity][k]);}
assert.deepEqual([sun,spot,point,vertical].map(snapshot),before,'export also leaves live sources unchanged');
console.log('Real GLB SUN/SPOT world-axis alignment, transformed parents, intensity and original immutability passed');
